"""Reseller levels and sanctions (reseller policy, sections 9 and 10)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.cash.domain.rules import Level
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Order
from apps.sales.models import Sale
from apps.sales.selectors import validated_sales
from apps.standing.adapters.gateways import AccountsResellers
from apps.standing.domain import rules
from apps.standing.models import ResellerLevel, Sanction
from apps.standing.repositories import StandingRepository
from apps.standing.services.standing import LevelService

pytestmark = pytest.mark.django_db

STANDING = "/api/v1/bo/standing/"
SANCTIONS = "/api/v1/bo/sanctions/"
ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Ibanda",
    "city": "Bukavu",
    "country": "RD Congo",
}


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


@pytest.fixture
def manager():
    return ManagerFactory.create()


@pytest.fixture
def reseller():
    return ResellerFactory.create()


class FakePerformance:
    def __init__(self, sales: dict[int, Decimal], ratings: dict[int, Decimal | None]) -> None:
        self._sales = sales
        self._ratings = ratings

    def validated_sales(self, reseller_ids, *, since, validated_before):
        return {pk: self._sales.get(pk, Decimal(0)) for pk in reseller_ids}

    def ratings(self, reseller_ids):
        return {pk: self._ratings.get(pk) for pk in reseller_ids}


def review(sales, ratings):
    service = LevelService(
        StandingRepository(),
        FakePerformance(sales, ratings),
        AccountsResellers(),
        clock=timezone.now,
    )
    return service.review()


def open_sanction(manager, reseller, kind, *, days=None, urgent=False, key="sanction-000001"):
    body = {
        "reseller_id": reseller.pk,
        "kind": kind,
        "reason": "Retard de reversement.",
        "urgent": urgent,
    }
    if days is not None:
        body["days"] = days
    return as_api(manager).post(SANCTIONS, body, format="json", HTTP_IDEMPOTENCY_KEY=key)


class TestRules:
    @pytest.mark.parametrize(
        ("sales", "rating", "level"),
        [
            ("3000.00", "4.5", Level.AMBASSADOR),
            ("3000.00", "4.4", Level.CONFIRMED),
            ("1000.00", "4.0", Level.CONFIRMED),
            ("999.99", "5.0", Level.BEGINNER),
            ("5000.00", None, Level.BEGINNER),
        ],
    )
    def test_level_needs_both_sales_and_rating(self, sales, rating, level):
        assert rules.level_for(Decimal(sales), Decimal(rating) if rating else None) is level

    def test_reviewed_on_the_first_day_of_each_quarter(self):
        assert rules.is_review_day(date(2026, 1, 1))
        assert rules.is_review_day(date(2026, 10, 1))
        assert not rules.is_review_day(date(2026, 2, 1))
        assert not rules.is_review_day(date(2026, 4, 2))

    def test_three_months_back_keeps_a_valid_day(self):
        moment = datetime(2026, 5, 31, 12, tzinfo=timezone.get_current_timezone())
        assert rules.months_before(moment, 3).date() == date(2026, 2, 28)


class TestLevels:
    def test_new_reseller_is_a_beginner(self, reseller):
        body = as_api(reseller).get(STANDING).json()
        assert body["level"] == Level.BEGINNER.value
        assert body["next_level"] == Level.CONFIRMED.value
        assert body["next_sales"] == "1000.00"
        assert body["suspended_until"] is None

    def test_review_promotes_and_demotes(self, reseller):
        other = ResellerFactory.create()
        ResellerLevel.objects.create(reseller=other, level=Level.CONFIRMED.value)
        changes = review({reseller.pk: Decimal("3200.00")}, {reseller.pk: Decimal("4.8")})
        assert {(c.reseller_id, c.level) for c in changes} == {
            (reseller.pk, Level.AMBASSADOR),
            (other.pk, Level.BEGINNER),
        }
        record = ResellerLevel.objects.get(reseller=reseller)
        assert record.sales == Decimal("3200.00")
        assert record.reviewed_at is not None

    def test_level_sets_the_cash_cap(self, manager, reseller):
        review({reseller.pk: Decimal("1500.00")}, {reseller.pk: Decimal("4.2")})
        summary = as_api(manager).get("/api/v1/bo/cash/summary/", {"reseller_id": reseller.pk})
        assert summary.json()["cap"] == "1000.00"

    def test_validated_sales_skip_the_last_seven_days(self, reseller):
        product = ProductFactory.create(price=Decimal("100.00"))
        now = timezone.now()
        for days_ago, refunded in ((20, "50.00"), (2, "0.00")):
            Sale.objects.create(
                product=product,
                product_name=product.name,
                seller=reseller,
                quantity=2,
                unit_price=Decimal("400.00"),
                refunded_amount=Decimal(refunded),
                sold_at=now - timedelta(days=days_ago),
            )
        totals = validated_sales(
            [reseller.pk], since=now - timedelta(days=90), validated_before=now - timedelta(days=7)
        )
        assert totals == {reseller.pk: Decimal("750.00")}

    def test_staff_review_and_a_client_cannot_see(self, manager, reseller):
        assert as_api(manager).post(f"{STANDING}review/").json() == {"changed": 0}
        assert as_api(reseller).post(f"{STANDING}review/").status_code == 403
        assert as_api(UserFactory.create()).get(STANDING).status_code == 403
        staff_view = as_api(manager).get(STANDING, {"reseller_id": reseller.pk})
        assert staff_view.json()["reseller_id"] == reseller.pk


class TestSanctions:
    def test_a_warning_applies_at_once(self, manager, reseller, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            response = open_sanction(manager, reseller, "warning")
        assert response.status_code == 201, response.json()
        assert response.json()["status"] == "applied"
        assert response.json()["explain_until"] is None
        assert reseller.notifications.filter(kind="sanction").exists()

    def test_suspension_waits_for_the_hearing(self, manager, reseller):
        response = open_sanction(manager, reseller, "suspension", days=7)
        body = response.json()
        assert body["status"] == "notified"
        assert body["explain_until"] is not None
        decide = as_api(manager).post(f"{SANCTIONS}{body['id']}/decide/", {"apply": True})
        assert decide.status_code == 422
        assert decide.json()["code"] == "hearing_pending"

    def test_explained_then_applied_blocks_new_orders(self, manager, reseller):
        sanction_id = open_sanction(manager, reseller, "suspension", days=10).json()["id"]
        explain = as_api(reseller).post(
            f"{SANCTIONS}{sanction_id}/explain/", {"explanation": "J'étais malade."}
        )
        assert explain.json()["explanation"] == "J'étais malade."
        decided = as_api(manager).post(f"{SANCTIONS}{sanction_id}/decide/", {"apply": True})
        assert decided.json()["status"] == "applied"
        ends_at = Sanction.objects.get(pk=sanction_id).ends_at
        assert ends_at is not None
        assert (ends_at - timezone.now()).days in (9, 10)
        assert as_api(reseller).get(STANDING).json()["suspended_until"] is not None

        order = self_checkout()
        assigned = as_api(manager).post(
            f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk}
        )
        assert assigned.status_code == 422
        assert assigned.json()["code"] == "reseller_suspended"
        assignable = as_api(manager).get("/api/v1/bo/resellers/assignable/").json()
        mine = next(row for row in assignable if row["id"] == reseller.pk)
        assert mine["suspended_until"] is not None

    def test_after_48_hours_it_can_be_applied(self, manager, reseller):
        sanction_id = open_sanction(manager, reseller, "suspension", days=7).json()["id"]
        Sanction.objects.filter(pk=sanction_id).update(
            explain_until=timezone.now() - timedelta(minutes=1)
        )
        late = as_api(reseller).post(f"{SANCTIONS}{sanction_id}/explain/", {"explanation": "x"})
        assert late.json()["code"] == "explanation_closed"
        decided = as_api(manager).post(f"{SANCTIONS}{sanction_id}/decide/", {"apply": True})
        assert decided.json()["status"] == "applied"

    def test_dropped_sanction_is_closed(self, manager, reseller):
        sanction_id = open_sanction(manager, reseller, "suspension", days=7).json()["id"]
        dropped = as_api(manager).post(
            f"{SANCTIONS}{sanction_id}/decide/", {"apply": False, "note": "Explication reçue."}
        )
        assert dropped.json()["status"] == "dropped"
        again = as_api(manager).post(f"{SANCTIONS}{sanction_id}/decide/", {"apply": True})
        assert again.json()["code"] == "sanction_closed"
        assert as_api(reseller).get(STANDING).json()["suspended_until"] is None

    def test_urgent_exclusion_closes_the_account(self, manager, reseller):
        response = open_sanction(manager, reseller, "exclusion", urgent=True)
        assert response.json()["status"] == "applied"
        reseller.refresh_from_db()
        assert not reseller.is_active

    @pytest.mark.parametrize("days", [None, 6, 31])
    def test_suspension_lasts_7_to_30_days(self, manager, reseller, days):
        response = open_sanction(manager, reseller, "suspension", days=days)
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_suspension"

    def test_only_the_reseller_explains_and_only_staff_sanction(self, manager, reseller):
        sanction_id = open_sanction(manager, reseller, "suspension", days=7).json()["id"]
        other = ResellerFactory.create()
        forbidden = as_api(other).post(f"{SANCTIONS}{sanction_id}/explain/", {"explanation": "x"})
        assert forbidden.status_code == 403
        assert open_sanction(reseller, other, "warning", key="sanction-000002").status_code == 403
        assert as_api(reseller).get(SANCTIONS).status_code == 403
        listed = as_api(manager).get(SANCTIONS, {"reseller_id": reseller.pk}).json()
        assert listed["meta"]["count"] == 1

    def test_a_client_cannot_be_sanctioned(self, manager):
        response = open_sanction(manager, UserFactory.create(), "warning")
        assert response.json()["code"] == "not_a_reseller"


def self_checkout() -> Order:
    product = ProductFactory.create(price=Decimal("100.00"), stock=10)
    response = as_api(UserFactory.create()).post(
        "/api/v1/orders/",
        {
            "lines": [{"product_id": product.pk, "quantity": 1}],
            "payment_method": "cash",
            "address": ADDRESS,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="checkout-standing-1",
    )
    assert response.status_code == 201, response.json()
    return Order.objects.get(pk=response.json()["id"])

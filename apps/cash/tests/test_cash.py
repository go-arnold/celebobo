"""Cash collected by resellers (reseller policy, section 6): remitted within 24 hours, capped by
level; late or over the cap, no new orders."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.cash.domain.rules import CashPosition, Level
from apps.cash.models import CashCollection, CashRemittance
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Order, ShippingZone

pytestmark = pytest.mark.django_db

ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Ibanda",
    "city": "Bukavu",
    "country": "RD Congo",
}
BO = "/api/v1/bo/orders/"
CASH = "/api/v1/bo/cash/"


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


@pytest.fixture
def make_order(manager):
    counter = iter(range(1, 1000))

    def make(price: str = "100.00", *, pickup: bool = False) -> Order:
        product = ProductFactory.create(price=Decimal(price), stock=10)
        response = as_api(UserFactory.create()).post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": product.pk, "quantity": 1}],
                "payment_method": "cash",
                "address": ADDRESS,
                "pickup": pickup,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"checkout-{next(counter):06d}",
        )
        assert response.status_code == 201, response.json()
        return Order.objects.get(pk=response.json()["id"])

    return make


def assign(manager, order, reseller):
    return as_api(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})


def pay(reseller, order, capture):
    api = as_api(reseller)
    with capture(execute=True):
        for status in ("confirmed", "paid"):
            assert api.post(f"{BO}{order.pk}/transition/", {"to": status}).status_code == 200


def summary(user, reseller=None):
    params = {"reseller_id": reseller.pk} if reseller else {}
    return as_api(user).get(f"{CASH}summary/", params).json()


def remit(manager, reseller, amount, key="remit-000001"):
    return as_api(manager).post(
        f"{CASH}remittances/",
        {"reseller_id": reseller.pk, "amount": amount, "reference": "MP-7731"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


class TestRules:
    def test_late_comes_before_the_cap(self):
        def position(held, overdue):
            return CashPosition(
                reseller_id=1,
                level=Level.BEGINNER,
                cap=Level.BEGINNER.cash_cap,
                held=Decimal(held),
                overdue=Decimal(overdue),
                oldest_due=None,
            )

        assert position("100", "0").blocked_reason is None
        assert "300.00 $" in (position("300", "0").blocked_reason or "")
        assert "24 heures" in (position("50", "50").blocked_reason or "")

    def test_caps_by_level(self):
        assert [level.cash_cap for level in Level] == [
            Decimal("300.00"),
            Decimal("1000.00"),
            Decimal("2500.00"),
        ]


class TestCollection:
    def test_paid_means_collected_due_within_24_hours(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        order = make_order()
        assign(manager, order, reseller)

        pay(reseller, order, django_capture_on_commit_callbacks)

        collection = CashCollection.objects.get(order=order)
        assert (collection.reseller_id, collection.amount) == (reseller.pk, order.total)
        assert collection.due_at - collection.collected_at == timedelta(hours=24)
        mine = summary(reseller)
        assert Decimal(mine["held"]) == order.total
        assert mine["blocked_reason"] is None
        assert mine["collections"][0]["order_number"] == order.number

    def test_once_per_order_and_none_for_a_pickup(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        # a pickup zone, as the delivery policy has (paid at the shop)
        ShippingZone.objects.create(
            name="Retrait sur place",
            fee=Decimal(0),
            pricing="pickup",
            pickup_address="Avenue Mwanga n° 21, Nyalukemba, Bukavu",
        )
        order = make_order()
        pickup = make_order(pickup=True)
        for each in (order, pickup):
            assign(manager, each, reseller)
            pay(reseller, each, django_capture_on_commit_callbacks)
        with django_capture_on_commit_callbacks(execute=True):
            as_api(manager).post(
                f"{BO}{order.pk}/transition/",
                {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
            )

        assert list(CashCollection.objects.values_list("order_id", flat=True)) == [order.pk]

    def test_a_cancelled_order_owes_nothing(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        order = make_order()
        assign(manager, order, reseller)
        pay(reseller, order, django_capture_on_commit_callbacks)

        with django_capture_on_commit_callbacks(execute=True):
            as_api(manager).post(f"{BO}{order.pk}/transition/", {"to": "cancelled"})

        assert CashCollection.objects.get(order=order).voided_at is not None
        assert summary(reseller)["held"] == "0.00"


class TestBlocking:
    def test_over_the_cap_no_new_orders(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        big = make_order("320.00")
        assign(manager, big, reseller)
        pay(reseller, big, django_capture_on_commit_callbacks)

        refused = assign(manager, make_order(), reseller)
        listing = as_api(manager).get("/api/v1/bo/resellers/assignable/").json()

        assert refused.status_code == 422
        assert refused.json()["code"] == "reseller_cash_blocked"
        row = next(item for item in listing if item["id"] == reseller.pk)
        assert "plafond" in row["cash_blocked"]

    def test_after_24_hours_no_new_orders(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        order = make_order()
        assign(manager, order, reseller)
        pay(reseller, order, django_capture_on_commit_callbacks)
        CashCollection.objects.update(due_at=timezone.now() - timedelta(minutes=1))

        refused = assign(manager, make_order(), reseller)

        assert refused.json()["code"] == "reseller_cash_blocked"
        assert "24 heures" in refused.json()["meta"]["reason"]

    def test_remitting_unblocks(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        big = make_order("320.00")
        assign(manager, big, reseller)
        pay(reseller, big, django_capture_on_commit_callbacks)

        response = remit(manager, reseller, str(big.total))

        assert response.status_code == 201, response.json()
        assert response.json()["held"] == "0.00"
        assert assign(manager, make_order(), reseller).status_code == 200
        assert CashRemittance.objects.get().recorded_by_id == manager.pk


class TestRemittances:
    def test_oldest_first_and_never_more_than_held(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        first, second = make_order("50.00"), make_order("60.00")
        for order in (first, second):
            assign(manager, order, reseller)
            pay(reseller, order, django_capture_on_commit_callbacks)

        too_much = remit(manager, reseller, "500.00")
        part = remit(manager, reseller, str(first.total + Decimal("10.00")), key="remit-000002")

        assert too_much.json()["code"] == "remittance_exceeds_held"
        assert CashCollection.objects.get(order=first).covered == first.total
        assert CashCollection.objects.get(order=second).covered == Decimal("10.00")
        assert Decimal(part.json()["held"]) == second.total - Decimal("10.00")

    def test_only_resellers_receive_remittances(self, manager):
        response = remit(manager, UserFactory.create(), "10.00")

        assert response.json()["code"] == "not_a_reseller"


class TestAccess:
    def test_resellers_see_their_own_staff_see_all(
        self, manager, reseller, make_order, django_capture_on_commit_callbacks
    ):
        order = make_order()
        assign(manager, order, reseller)
        pay(reseller, order, django_capture_on_commit_callbacks)
        other = ResellerFactory.create()

        own = summary(other, reseller)
        overview = as_api(manager).get(CASH).json()
        forbidden = as_api(reseller).get(CASH)
        staff_remit = remit(reseller, reseller, "10.00", key="remit-000003")

        # a reseller asking for someone else gets their own position
        assert own["reseller_id"] == other.pk
        assert [row["reseller_id"] for row in overview] == [reseller.pk]
        assert forbidden.status_code == 403
        assert staff_remit.status_code == 403

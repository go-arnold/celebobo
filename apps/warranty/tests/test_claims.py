"""Warranty claims (warranty policy): the windows, the steps, the outcomes."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem
from apps.warranty.domain import rules
from apps.warranty.domain.events import ClaimSubmitted, ClaimUpdated
from apps.warranty.models import Claim
from apps.warranty.tests.conftest import IMEI, delivered_days_ago

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/claims/"
BO = "/api/v1/bo/claims/"


def claimable(api, order: Order) -> dict[str, Any]:
    response = api.get(f"/api/v1/me/orders/{order.pk}/claimable/")
    assert response.status_code == 200, response.json()
    line: dict[str, Any] = response.json()[0]
    return line


def submit(api, order: Order, kind="defect", serial=IMEI, key="claim-000001"):
    return api.post(
        MINE,
        {
            "order_id": order.pk,
            "item_id": order.items.get().pk,
            "kind": kind,
            "description": "L'écran reste noir depuis ce matin.",
            "serial": serial,
            "photos": ["https://res.cloudinary.com/demo/ecran.jpg"],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def step(api, claim_id: int, action: str, payload: dict[str, Any] | None = None, key: str = ""):
    extra = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    return api.post(f"{BO}{claim_id}/{action}/", payload or {}, format="json", **extra)


def diagnose(api, claim_id: int, key="diagnose-0001", **payload):
    return step(api, claim_id, "diagnose", payload, key=key)


def received_claim(as_user, shopper, manager, order: Order, kind="defect") -> int:
    claim_id: int = submit(as_user(shopper), order, kind=kind).json()["id"]
    staff = as_user(manager)
    assert step(staff, claim_id, "answer", {"return_method": "shop"}).status_code == 200
    assert step(staff, claim_id, "receive", {}).status_code == 200
    return claim_id


class TestRules:
    def test_working_days_skip_sundays(self):
        saturday = timezone.make_aware(datetime(2026, 11, 21, 10))
        assert rules.add_working_days(saturday, 1).weekday() == 0
        assert rules.add_working_days(saturday, 3).day == 25

    def test_windows(self):
        delivered = timezone.localdate()
        ordered = delivered - timedelta(days=1)
        later = {
            "trial": delivered + timedelta(days=7),
            "warranty": delivered + timedelta(days=20),
            "after": delivered + timedelta(days=40),
        }

        def cover(kind, day, extension=0):
            return rules.protection_for(
                kind,
                ordered_on=ordered,
                delivered_on=delivered,
                today=day,
                extension_days=extension,
            )

        assert cover(rules.ClaimKind.CHANGE_OF_MIND, later["trial"]) is rules.Protection.TRIAL
        assert cover(rules.ClaimKind.CHANGE_OF_MIND, later["warranty"]) is None
        assert cover(rules.ClaimKind.DEFECT, later["warranty"]) is rules.Protection.WARRANTY
        assert cover(rules.ClaimKind.DEFECT, later["after"]) is None
        assert cover(rules.ClaimKind.DEFECT, later["after"], 15) is rules.Protection.WARRANTY
        assert cover(rules.ClaimKind.COUNTERFEIT, later["after"]) is rules.Protection.AUTHENTICITY


class TestSubmitting:
    def test_what_a_line_can_be_claimed_for(self, as_user, shopper, delivered):
        api = as_user(shopper)

        today = claimable(api, delivered)
        delivered_days_ago(delivered, 10)
        later = claimable(api, delivered)

        assert today["kinds"] == ["defect", "change_of_mind", "counterfeit"]
        assert today["serials"] == [IMEI]
        assert later["kinds"] == ["defect", "counterfeit"]

    def test_a_defect_during_the_trial(self, as_user, shopper, delivered, published_events):
        response = submit(as_user(shopper), delivered)

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["status"], body["protection"], body["serial"]) == ("submitted", "trial", IMEI)
        assert body["number"] == f"RC-{body['id']:05d}"
        event = published_events.single(ClaimSubmitted)
        assert (event.product, event.number) == ("Galaxy A55", body["number"])

    def test_the_serial_must_be_the_one_on_the_invoice(self, as_user, shopper, delivered):
        response = submit(as_user(shopper), delivered, serial="490154203237518")

        assert response.status_code == 400
        assert response.json()["code"] == "serial_not_on_order"

    def test_a_change_of_mind_after_the_trial_is_refused(self, as_user, shopper, delivered):
        delivered_days_ago(delivered, 10)

        response = submit(as_user(shopper), delivered, kind="change_of_mind")

        assert response.status_code == 422
        assert response.json()["code"] == "claim_window_closed"

    def test_one_claim_at_a_time_per_line(self, as_user, shopper, delivered):
        api = as_user(shopper)
        submit(api, delivered)

        again = submit(api, delivered, key="claim-000002")

        assert again.status_code == 409
        assert again.json()["code"] == "claim_already_open"

    def test_only_the_client_and_only_once_delivered(
        self, as_user, shopper, tracked, place_order, delivered
    ):
        other = submit(as_user(UserFactory.create()), delivered)
        pending = Order.objects.get(number=place_order(shopper, tracked)["number"])
        early = submit(as_user(shopper), pending, serial="", key="claim-000003")

        assert other.status_code == 404
        assert early.json()["code"] == "line_not_claimable"


class TestHandling:
    def test_a_repair_extends_the_warranty(self, as_user, shopper, manager, delivered):
        claim_id = received_claim(as_user, shopper, manager, delivered)
        staff = as_user(manager)

        repairing = diagnose(staff, claim_id, covered=True, outcome="repair").json()
        Claim.objects.filter(pk=claim_id).update(received_at=timezone.now() - timedelta(days=12))
        closed = step(staff, claim_id, "repaired", {"note": "Écran remplacé"}).json()

        assert repairing["status"] == "repairing"
        assert repairing["outcome_due"] is not None
        assert (closed["status"], closed["outcome"]) == ("closed", "repair")
        # 12 days in repair: the warranty runs 12 more days
        delivered_days_ago(delivered, 40)
        assert claimable(as_user(shopper), delivered)["kinds"] == ["defect", "counterfeit"]

    def test_a_refund_takes_the_unit_back_through_the_order(
        self, as_user, shopper, manager, delivered
    ):
        claim_id = received_claim(as_user, shopper, manager, delivered)

        body = diagnose(as_user(manager), claim_id, covered=True, outcome="refund").json()

        assert (body["status"], body["outcome"]) == ("closed", "refund")
        item = OrderItem.objects.get(pk=delivered.items.get().pk)
        assert item.returned_quantity == 1
        assert body["outcome_due"] is not None
        assert body["closed_at"] is not None

    def test_an_exchange_keeps_15_days_of_warranty_at_least(
        self, as_user, shopper, manager, delivered
    ):
        delivered_days_ago(delivered, 25)
        claim_id = received_claim(as_user, shopper, manager, delivered)

        body = diagnose(
            as_user(manager),
            claim_id,
            covered=True,
            outcome="exchange",
            new_serial="490154203237518",
        ).json()

        assert body["new_serial"] == "490154203237518"
        until = date.fromisoformat(body["exchange_warranty_until"])
        assert until >= timezone.localdate() + timedelta(days=15)

    def test_not_covered_with_a_quote(self, as_user, shopper, manager, delivered, published_events):
        claim_id = received_claim(as_user, shopper, manager, delivered)

        body = diagnose(
            as_user(manager), claim_id, covered=False, outcome="not_covered", quote="25.00"
        ).json()

        assert (body["covered"], body["quote"]) == (False, "25.00")
        last = published_events.of_type(ClaimUpdated)[-1]
        assert "25.00 $" in last.message
        assert last.client_id == shopper.pk

    def test_a_change_of_mind_can_become_store_credit(
        self, as_user, shopper, manager, delivered, django_capture_on_commit_callbacks
    ):
        from apps.credit.models import CreditEntry

        claim_id = received_claim(as_user, shopper, manager, delivered, kind="change_of_mind")

        with django_capture_on_commit_callbacks(execute=True):
            body = diagnose(as_user(manager), claim_id, covered=True, outcome="store_credit").json()

        assert (body["status"], body["outcome"]) == ("closed", "store_credit")
        credit = CreditEntry.objects.get(user=shopper, kind="issued")
        # what the client paid for the phone, as store credit valid 6 months
        assert credit.amount == OrderItem.objects.get(order=delivered).amount_paid
        assert OrderItem.objects.get(order=delivered).returned_quantity == 1

    def test_outcomes_follow_the_kind(self, as_user, shopper, manager, delivered):
        claim_id = received_claim(as_user, shopper, manager, delivered, kind="change_of_mind")

        response = diagnose(as_user(manager), claim_id, covered=True, outcome="refund")

        assert response.json()["code"] == "outcome_not_allowed"

    def test_sealed_only_products_need_the_seal(self, as_user, shopper, manager, delivered):
        OrderItem.objects.filter(order=delivered).update(sealed_return_only=True)
        claim_id = submit(as_user(shopper), delivered, kind="change_of_mind").json()["id"]
        staff = as_user(manager)
        step(staff, claim_id, "receive", {"sealed": False})

        refused = diagnose(staff, claim_id, covered=True, outcome="exchange")
        given_back = diagnose(
            staff, claim_id, key="diagnose-0002", covered=False, outcome="not_covered"
        )

        assert refused.json()["code"] == "seal_required"
        assert given_back.json()["outcome"] == "not_covered"

    def test_steps_come_in_order(self, as_user, shopper, manager, delivered):
        claim_id = submit(as_user(shopper), delivered).json()["id"]

        response = diagnose(as_user(manager), claim_id, covered=True, outcome="repair")

        assert response.json()["code"] == "claim_step_not_allowed"

    def test_overdue_answers_show(self, as_user, shopper, manager, delivered):
        claim_id = submit(as_user(shopper), delivered).json()["id"]
        Claim.objects.filter(pk=claim_id).update(answer_due=timezone.now() - timedelta(hours=1))

        assert as_user(manager).get(f"{BO}{claim_id}/").json()["overdue"] is True


class TestAccess:
    def test_clients_follow_their_own_claims_only(self, as_user, shopper, delivered):
        claim_id = submit(as_user(shopper), delivered).json()["id"]

        mine = as_user(shopper).get(MINE).json()
        other = as_user(UserFactory.create()).get(f"{MINE}{claim_id}/")
        backoffice = as_user(shopper).get(BO)

        assert [claim["id"] for claim in mine["results"]] == [claim_id]
        assert other.status_code == 404
        assert backoffice.status_code == 403

    def test_staff_list_and_filter(self, as_user, shopper, manager, delivered):
        claim_id = submit(as_user(shopper), delivered).json()["id"]

        listing = as_user(manager).get(BO, {"status": "submitted"}).json()

        assert [claim["id"] for claim in listing["results"]] == [claim_id]
        assert listing["results"][0]["kind_label"] == "Produit défectueux ou non conforme"


def test_the_product_setting(as_user, manager, phone):
    response = as_user(manager).patch(
        f"/api/v1/bo/products/{phone.pk}/", {"sealed_return_only": True}, format="json"
    )

    assert response.json()["sealed_return_only"] is True
    assert Product.objects.get(pk=phone.pk).sealed_return_only is True

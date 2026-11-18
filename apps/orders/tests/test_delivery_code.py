import re

import pytest

from apps.orders.domain.events import (
    DeliveredWithoutCode,
    DeliveryCodeIssued,
    DeliveryCodeLocked,
)
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"


@pytest.fixture
def order(as_user, shopper, phone, place_order, *, manager, reseller) -> Order:
    number = place_order(shopper, phone)["number"]
    order = Order.objects.get(number=number)
    as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    return order


def move(api, order, status, **extra):
    return api.post(f"{BO}{order.pk}/transition/", {"to": status, **extra})


def out_for_delivery(api, order) -> str:
    for status in ("confirmed", "paid", "shipping"):
        assert move(api, order, status).status_code == 200
    order.refresh_from_db()
    return str(order.delivery_code)


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


class TestIssuing:
    def test_confirmation_gives_the_client_a_code_the_back_office_never_sees(
        self, as_user, shopper, reseller, order, published_events
    ):
        before = as_user(shopper).get(f"{MINE}{order.number}/").json()
        move(as_user(reseller), order, "confirmed")

        order.refresh_from_db()
        mine = as_user(shopper).get(f"{MINE}{order.number}/").json()
        staff = as_user(reseller).get(f"{BO}{order.pk}/").json()
        assert before["delivery_code"] is None
        assert re.fullmatch(r"\d{6}", order.delivery_code)
        assert mine["delivery_code"] == order.delivery_code
        assert "delivery_code" not in staff
        assert order.delivery_code not in str(staff)
        # every event is kept in the audit log: never the code itself
        assert order.delivery_code not in repr(published_events.single(DeliveryCodeIssued))

    def test_skipping_confirmation_still_issues_the_code(self, as_user, manager, order):
        move(as_user(manager), order, "paid")

        order.refresh_from_db()
        assert re.fullmatch(r"\d{6}", order.delivery_code)


class TestHandover:
    def test_the_reseller_delivers_with_the_clients_code(self, as_user, shopper, reseller, order):
        api = as_user(reseller)
        code = out_for_delivery(api, order)

        missing = move(api, order, "delivered")
        refused = move(api, order, "delivered", delivery_code=wrong(code))
        delivered = move(api, order, "delivered", delivery_code=code)

        assert missing.json()["code"] == "delivery_code_required"
        assert refused.json()["code"] == "invalid_delivery_code"
        assert refused.json()["meta"]["attempts_left"] == 4
        assert delivered.json()["status"] == "delivered"
        order.refresh_from_db()
        assert order.delivery_code_attempts == 1
        # delivered: the client no longer needs it on screen
        assert as_user(shopper).get(f"{MINE}{order.number}/").json()["delivery_code"] is None

    def test_five_wrong_codes_lock_it_and_alert_staff(
        self, as_user, reseller, order, published_events
    ):
        api = as_user(reseller)
        code = out_for_delivery(api, order)

        answers = [move(api, order, "delivered", delivery_code=wrong(code)) for _ in range(5)]
        after = move(api, order, "delivered", delivery_code=code)

        assert [r.json()["meta"].get("attempts_left") for r in answers[:4]] == [4, 3, 2, 1]
        assert answers[4].json()["code"] == "delivery_code_locked"
        assert after.json()["code"] == "delivery_code_locked"
        order.refresh_from_db()
        assert (order.status, order.delivery_code_locked_at is not None) == ("shipping", True)
        assert len(published_events.of_type(DeliveryCodeLocked)) == 1
        staff_view = as_user(reseller).get(f"{BO}{order.pk}/").json()
        assert staff_view["delivery_code_locked"] is True

    def test_a_manager_confirms_without_the_code_with_a_reason(
        self, as_user, manager, reseller, order, published_events
    ):
        out_for_delivery(as_user(reseller), order)
        api = as_user(manager)

        silent = move(api, order, "delivered")
        delivered = move(api, order, "delivered", reason="  Client joint par téléphone  ")

        assert silent.json()["code"] == "delivery_reason_required"
        assert delivered.json()["status"] == "delivered"
        assert published_events.single(DeliveredWithoutCode).reason == "Client joint par téléphone"

    def test_a_manager_may_also_enter_the_code(self, as_user, manager, reseller, order):
        code = out_for_delivery(as_user(reseller), order)

        response = move(as_user(manager), order, "delivered", delivery_code=code)

        assert response.json()["status"] == "delivered"

    def test_the_code_has_six_digits(self, as_user, reseller, order):
        out_for_delivery(as_user(reseller), order)

        response = move(as_user(reseller), order, "delivered", delivery_code="12ab")

        assert response.status_code == 400
        assert "delivery_code" in response.json()["errors"]

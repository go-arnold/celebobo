from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import ResellerFactory
from apps.orders.domain.attempts import working_days
from apps.orders.domain.events import DeliveryAttemptFailed, RefundDue
from apps.orders.models import DeliveryAttempt, Order

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"


@pytest.fixture
def order(as_user, shopper, phone, place_order, *, manager, reseller) -> Order:
    order = Order.objects.get(number=place_order(shopper, phone)["number"])
    as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    api = as_user(reseller)
    for status in ("confirmed", "paid", "shipping"):
        assert api.post(f"{BO}{order.pk}/transition/", {"to": status}).status_code == 200
    order.refresh_from_db()
    return order


def attempt(api, order, reason="client_absent", note=""):
    return api.post(f"{BO}{order.pk}/delivery-attempts/", {"reason": reason, "note": note})


def failed_on(order, *days: date) -> None:
    """Earlier failed attempts, on fixed days: the tests do not depend on today's weekday."""
    for day in days:
        DeliveryAttempt.objects.create(
            order=order,
            reason="client_absent",
            created_at=timezone.make_aware(datetime(day.year, day.month, day.day, 10)),
        )


MONDAY, TUESDAY = date(2026, 11, 16), date(2026, 11, 17)


class TestWorkingDays:
    def test_sundays_and_repeated_days_do_not_count(self):
        monday, sunday = date(2026, 11, 16), date(2026, 11, 22)

        assert working_days([monday, monday]) == 1
        assert working_days([sunday, sunday]) == 0
        assert working_days([monday, sunday, monday + timedelta(days=1)]) == 2


class TestAttempts:
    def test_a_failed_attempt_is_recorded_and_the_order_stays_out(
        self, as_user, shopper, reseller, order, published_events
    ):
        response = attempt(as_user(reseller), order, note="  Personne à la maison  ")
        again = attempt(as_user(reseller), order, "unreachable")

        assert response.status_code == 200, response.json()
        assert response.json()["delivery_attempts"][0]["reason_label"] == "Client absent"
        assert response.json()["delivery_attempts"][0]["note"] == "Personne à la maison"
        # a second attempt the same day is not a second day
        assert again.json()["status"] == "shipping"
        assert [e.days for e in published_events.of_type(DeliveryAttemptFailed)] == [1, 1]
        mine = as_user(shopper).get(f"{MINE}{order.number}/").json()
        assert len(mine["delivery_attempts"]) == 2

    def test_failures_on_two_working_days_cancel_with_the_fee_kept(
        self, as_user, reseller, phone, order, published_events
    ):
        failed_on(order, MONDAY, TUESDAY)

        # recording an attempt checks the days: two working days of failures cancel the order
        response = attempt(as_user(reseller), order, "unreachable")

        body = response.json()
        order.refresh_from_db()
        assert body["status"] == "cancelled"
        assert order.cancel_reason == "delivery_failed"
        assert order.refund_due == order.total - order.shipping_fee
        assert body["refund_due"] == str(order.total - order.shipping_fee)
        due = published_events.single(RefundDue)
        assert (due.amount, due.delivery_failed) == (order.total - order.shipping_fee, True)
        phone.refresh_from_db()
        assert phone.stock == 5

    def test_only_while_out_for_delivery(self, as_user, shopper, phone, place_order, manager):
        pending = Order.objects.get(number=place_order(shopper, phone)["number"])

        response = attempt(as_user(manager), pending)

        assert response.json()["code"] == "attempt_not_allowed"

    def test_only_the_assigned_reseller_or_staff(self, as_user, shopper, manager, order):
        assert attempt(as_user(ResellerFactory.create()), order).status_code == 404
        assert attempt(as_user(shopper), order).status_code == 403
        assert attempt(as_user(manager), order).status_code == 200

    def test_the_client_cannot_pick_the_system_reasons(self, as_user, shopper, phone, place_order):
        number = place_order(shopper, phone)["number"]

        response = as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "delivery_failed"})

        assert response.status_code == 400

    def test_a_free_delivery_refunds_everything(self, as_user, reseller, order):
        Order.objects.filter(pk=order.pk).update(
            shipping_fee=Decimal(0), total=order.subtotal - order.discount - order.points
        )
        failed_on(order, MONDAY, TUESDAY)

        attempt(as_user(reseller), order)

        order.refresh_from_db()
        assert order.refund_due == order.total

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from apps.orders.models import Order, OrderStatusEvent
from apps.orders.tasks import EXPIRE_TASK, expire_stale_orders
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"


def age(order: Order, hours: float) -> None:
    then = timezone.now() - timedelta(hours=hours)
    Order.objects.filter(pk=order.pk).update(created_at=then)
    OrderStatusEvent.objects.filter(order=order).update(created_at=then)


def stock_of(product: Product) -> int:
    product.refresh_from_db()
    return product.stock


@pytest.fixture
def placed(place_order, shopper, phone) -> Callable[..., Order]:
    def place(*, hours: float = 0) -> Order:
        order = Order.objects.get(number=place_order(shopper, phone)["number"])
        if hours:
            age(order, hours)
        return order

    return place


@pytest.fixture
def assign(as_user, manager, reseller) -> Callable[[Order], None]:
    def run(order: Order) -> None:
        response = as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
        assert response.status_code == 200

    return run


class TestExpiry:
    def test_unassigned_order_is_cancelled_after_48_hours_and_restocked(self, placed, phone):
        order = placed(hours=49)
        assert stock_of(phone) == 4

        assert expire_stale_orders() == 1

        order.refresh_from_db()
        assert order.status == "cancelled"
        assert order.cancel_reason == "expired"
        assert "48 h" in order.cancel_details
        assert stock_of(phone) == 5
        last = order.history.last()
        assert last.to_status == "cancelled"
        assert last.actor_role == "system"

    def test_client_is_told_through_the_status_event(self, placed, published_events):
        order = placed(hours=49)

        expire_stale_orders()

        changes = [e for e in published_events.events if isinstance(e, OrderStatusChanged)]
        assert [(e.order_id, e.status, e.actor_id) for e in changes] == [
            (order.pk, OrderStatus.CANCELLED, None)
        ]

    def test_recent_and_assigned_orders_are_kept(self, placed, assign):
        recent = placed(hours=47)
        assigned = placed()
        assign(assigned)
        age(assigned, 72)

        assert expire_stale_orders() == 0

        assert Order.objects.get(pk=recent.pk).status == "pending"
        assert Order.objects.get(pk=assigned.pk).status == "assigned"

    def test_delay_restarts_when_a_reseller_declines(self, as_user, reseller, placed, assign):
        order = placed()
        assign(order)
        age(order, 72)
        response = as_user(reseller).post(f"{BO}{order.pk}/decline/", {"reason": "Indisponible"})
        assert response.status_code == 204

        assert expire_stale_orders() == 0
        assert Order.objects.get(pk=order.pk).status == "pending"

    def test_runs_every_hour(self):
        assert settings.CELERY_BEAT_SCHEDULE["expire-stale-orders"] == {
            "task": EXPIRE_TASK,
            "schedule": 60 * 60,
        }


class TestPendingCap:
    def test_a_fourth_pending_order_is_refused(self, as_user, shopper, phone, placed):
        for _ in range(3):
            placed()

        response = as_user(shopper).post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": phone.pk, "quantity": 1}],
                "payment_method": "cash",
                "address": ADDRESS,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="checkout-cap-0004",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "too_many_pending_orders"
        assert response.json()["meta"]["limit"] == 3
        assert Order.objects.filter(client=shopper).count() == 3
        assert stock_of(phone) == 2

    def test_assigned_or_cancelled_orders_free_a_place(self, as_user, shopper, placed, assign):
        first, second, _ = (placed() for _ in range(3))
        assign(first)
        as_user(shopper).post(f"{MINE}{second.number}/cancel/", {"reason": "changed_mind"})

        placed()
        placed()

        assert Order.objects.filter(client=shopper, status="pending").count() == 3

    def test_clients_cannot_choose_the_expired_reason(self, as_user, shopper, placed):
        order = placed()

        response = as_user(shopper).post(f"{MINE}{order.number}/cancel/", {"reason": "expired"})

        assert response.status_code == 400
        assert Order.objects.get(pk=order.pk).status == "pending"

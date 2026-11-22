from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import Order, OrderItemSerial, OrderStatusEvent
from apps.orders.tests.conftest import (  # noqa: F401  (shared order fixtures)
    api,
    as_user,
    manager,
    phone,
    place_order,
    reseller,
    shopper,
)

BO = "/api/v1/bo/orders/"
IMEI = "352099001761481"


@pytest.fixture
def tracked(phone) -> Product:  # noqa: F811
    Product.objects.filter(pk=phone.pk).update(serial_required=True, price=Decimal("120.00"))
    product: Product = Product.objects.get(pk=phone.pk)
    return product


@pytest.fixture
def delivered(as_user, shopper, tracked, place_order, manager) -> Order:  # noqa: F811
    """An order of one phone (IMEI recorded) delivered today, for the shopper."""
    order = Order.objects.get(number=place_order(shopper, tracked)["number"])
    staff = as_user(manager)
    staff.post(f"{BO}{order.pk}/assign/", {"reseller_id": _reseller_id()})
    OrderItemSerial.objects.create(item=order.items.get(), serial=IMEI)
    response = staff.post(
        f"{BO}{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    return order


def _reseller_id() -> int:
    from apps.accounts.tests.factories import ResellerFactory

    reseller_id: int = ResellerFactory.create().pk
    return reseller_id


def delivered_days_ago(order: Order, days: int) -> None:
    moment = timezone.now() - timedelta(days=days)
    OrderStatusEvent.objects.filter(order=order, to_status="delivered").update(created_at=moment)
    Order.objects.filter(pk=order.pk).update(created_at=moment - timedelta(days=1))

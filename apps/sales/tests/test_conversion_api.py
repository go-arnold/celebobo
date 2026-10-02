from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.sales.domain.events import OrderConverted
from apps.sales.models import CommissionEntry, Sale

pytestmark = pytest.mark.django_db

BO_ORDERS = "/api/v1/bo/orders/"
SALES = "/api/v1/bo/sales/"


@pytest.fixture
def order(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])


@pytest.fixture
def confirmed(as_user, manager, reseller, order: Order) -> Order:
    api = as_user(manager)
    assert (
        api.post(f"{BO_ORDERS}{order.pk}/assign/", {"reseller_id": reseller.pk}).status_code == 200
    )
    assert api.post(f"{BO_ORDERS}{order.pk}/transition/", {"to": "confirmed"}).status_code == 200
    order.refresh_from_db()
    return order


def convert(api, order, key="convert-000001", **payload):
    return api.post(
        f"{BO_ORDERS}{order.pk}/convert-to-sales/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def stock_of(product: Product) -> int:
    product.refresh_from_db()
    return product.stock


class TestConvertible:
    def test_lists_confirmed_orders_and_flags_converted_ones(self, as_user, reseller, confirmed):
        api = as_user(reseller)
        before = api.get(f"{BO_ORDERS}convertible/").json()
        convert(api, confirmed)
        after = api.get(f"{BO_ORDERS}convertible/", {"search": confirmed.number}).json()

        assert [row["id"] for row in before] == [confirmed.pk]
        assert before[0]["convertible"] is True
        assert before[0]["items_count"] == 1
        assert after[0]["convertible"] is False
        assert after[0]["blocked_reason"] == "already_converted"

    def test_pending_orders_are_not_listed(self, as_user, manager, order):
        assert as_user(manager).get(f"{BO_ORDERS}convertible/").json() == []


class TestConversion:
    def test_creates_sales_without_moving_stock_and_delivers(
        self, as_user, reseller, phone, confirmed, published_events
    ):
        stock = stock_of(phone)

        response = convert(as_user(reseller), confirmed)

        assert response.status_code == 201
        (sale,) = response.json()
        assert sale["order_number"] == confirmed.number
        assert sale["seller"]["id"] == reseller.pk
        assert sale["sold_to"] == "Aline Mbuyi"
        assert sale["total"] == "240.00"
        assert sale["payment_method"] == "orange_money"
        assert stock_of(phone) == stock
        confirmed.refresh_from_db()
        assert confirmed.status == "delivered"
        assert CommissionEntry.objects.get().amount == Decimal("24.00")
        assert any(isinstance(event, OrderConverted) for event in published_events.events)

    def test_price_overrides_and_payment_method(self, as_user, manager, confirmed):
        item = confirmed.items.get()

        response = convert(
            as_user(manager),
            confirmed,
            payment_method="cash",
            lines=[{"item_id": item.pk, "unit_price": "110.00"}],
        )

        (sale,) = response.json()
        assert sale["unit_price"] == "110.00"
        assert sale["payment_method"] == "cash"

    def test_is_idempotent_per_order_item(self, as_user, reseller, confirmed):
        api = as_user(reseller)
        convert(api, confirmed)

        again = convert(api, confirmed, key="convert-000002")

        assert again.status_code == 409
        assert again.json()["meta"]["reason"] == "already_converted"
        assert Sale.objects.count() == 1

    def test_rejects_unknown_items_and_unconvertible_orders(
        self, as_user, manager, order, confirmed
    ):
        api = as_user(manager)

        unknown = convert(api, confirmed, lines=[{"item_id": 999999, "unit_price": "1.00"}])
        api.post(f"{BO_ORDERS}{confirmed.pk}/transition/", {"to": "cancelled"})
        cancelled = convert(api, confirmed, key="convert-000003")

        assert unknown.status_code == 400
        assert cancelled.status_code in (404, 409)
        assert not Sale.objects.exists()

    def test_other_resellers_cannot_convert(self, as_user, confirmed):
        from apps.accounts.tests.factories import ResellerFactory

        response = convert(as_user(ResellerFactory.create()), confirmed)

        assert response.status_code == 404


class TestOrderReturns:
    def test_returning_the_order_returns_its_sales_once(
        self, as_user, manager, phone, confirmed, django_capture_on_commit_callbacks
    ):
        api = as_user(manager)
        convert(api, confirmed)
        stock = stock_of(phone)

        with django_capture_on_commit_callbacks(execute=True):
            response = api.post(f"{BO_ORDERS}{confirmed.pk}/transition/", {"to": "returned"})

        assert response.status_code == 200
        sale = Sale.objects.get()
        assert sale.status == "returned"
        assert sale.refunded_amount == Decimal("240.00")
        assert stock_of(phone) == stock + 2
        assert sum(entry.amount for entry in CommissionEntry.objects.all()) == Decimal("0.00")
        stats = api.get(SALES).json()["meta"]["stats"]
        assert stats["revenue"] == "0.00"

    def test_order_linked_sales_cannot_be_returned_directly(self, as_user, manager, confirmed):
        (sale,) = convert(as_user(manager), confirmed).json()

        response = as_user(manager).post(
            f"{SALES}{sale['id']}/refund/",
            {"kind": "return"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="refund-000001",
        )

        assert response.status_code == 422
        assert response.json()["code"] == "return_through_order"

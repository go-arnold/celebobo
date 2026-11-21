from collections.abc import Callable
from decimal import Decimal
from unittest.mock import Mock

import pytest

from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.orders.domain.pricing import LineAmounts, returned_amounts
from apps.orders.models import Coupon, Order, OrderItem, OrderLineReturn
from apps.orders.tests.conftest import ADDRESS
from apps.sales.facades import SalesFacade

D = Decimal
BO = "/api/v1/bo/orders/"


class TestReturnedAmounts:
    def test_partial_returns_round_down_and_the_last_takes_the_rest(self):
        line = LineAmounts(discount=D("10.00"), points=D("0.00"), paid=D("290.00"))
        nothing = LineAmounts(discount=D(0), points=D(0), paid=D(0))

        first = returned_amounts(line, quantity=3, returned=0, returning=1, already=nothing)
        last = returned_amounts(line, quantity=3, returned=1, returning=2, already=first)

        assert (first.discount, first.paid) == (D("3.33"), D("96.66"))
        assert (last.discount, last.paid) == (D("6.67"), D("193.34"))


pytestmark = pytest.mark.django_db


@pytest.fixture
def products(db) -> tuple[Product, Product]:
    return (
        ProductFactory.create(price=D("100.00"), stock=10),
        ProductFactory.create(price=D("50.00"), stock=10),
    )


@pytest.fixture
def delivered(as_user, shopper, manager, reseller, products) -> Order:
    phone, case = products
    Coupon.objects.create(code="TRENTE", kind="fixed", value=D("30.00"))
    response = as_user(shopper).post(
        "/api/v1/orders/",
        {
            "lines": [
                {"product_id": phone.pk, "quantity": 2},
                {"product_id": case.pk, "quantity": 1},
            ],
            "payment_method": "cash",
            "address": ADDRESS,
            "coupon_code": "TRENTE",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="line-returns-0001",
    )
    order = Order.objects.get(number=response.json()["number"])
    staff = as_user(manager)
    staff.post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    staff.post(
        f"{BO}{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    order.refresh_from_db()
    assert order.status == "delivered"
    return order


@pytest.fixture
def give_back(as_user, manager) -> Callable[..., object]:
    keys = iter(range(1, 1000))

    def run(order: Order, item: OrderItem, quantity: int, *, user=None, reason: str = "Défaut"):
        return as_user(user or manager).post(
            f"{BO}{order.pk}/items/{item.pk}/return/",
            {"quantity": quantity, "reason": reason},
            format="json",
            HTTP_IDEMPOTENCY_KEY=f"line-return-{next(keys):06d}",
        )

    return run


def stock_of(product: Product) -> int:
    product.refresh_from_db()
    return product.stock


def lines_of(order: Order) -> tuple[OrderItem, OrderItem]:
    phone_line, case_line = order.items.order_by("pk")
    return phone_line, case_line


class TestLineReturn:
    def test_one_unit_comes_back_with_its_share(self, delivered, give_back, products):
        phone, _ = products
        phone_line, _ = lines_of(delivered)
        assert (phone_line.discount, phone_line.amount_paid) == (D("24.00"), D("176.00"))

        response = give_back(delivered, phone_line, 1)

        assert response.status_code == 200
        line = response.json()["items"][0]
        assert (line["returned_quantity"], line["returned_amount"]) == (1, "88.00")
        assert response.json()["status"] == "delivered"
        record = OrderLineReturn.objects.get()
        assert (record.quantity, record.discount, record.amount_paid) == (1, D("12.00"), D("88.00"))
        assert record.reason == "Défaut"
        assert stock_of(phone) == 9

    def test_returning_everything_returns_the_order_without_restocking_twice(
        self, delivered, give_back, products
    ):
        phone, case = products
        phone_line, case_line = lines_of(delivered)

        give_back(delivered, phone_line, 1)
        give_back(delivered, phone_line, 1)
        response = give_back(delivered, case_line, 1)

        assert response.json()["status"] == "returned"
        assert (stock_of(phone), stock_of(case)) == (10, 10)
        refunds = [entry.amount_paid for entry in OrderLineReturn.objects.order_by("pk")]
        assert refunds == [D("88.00"), D("88.00"), D("44.00")]
        assert sum(refunds) == delivered.subtotal - delivered.discount

    def test_returning_the_whole_order_after_a_line_restocks_only_the_rest(
        self, as_user, manager, delivered, give_back, products
    ):
        phone, case = products
        phone_line, _ = lines_of(delivered)
        give_back(delivered, phone_line, 1)

        as_user(manager).post(f"{BO}{delivered.pk}/transition/", {"to": "returned"})

        assert (stock_of(phone), stock_of(case)) == (10, 10)
        assert [item.returned_quantity for item in delivered.items.order_by("pk")] == [2, 1]


class TestRules:
    def test_only_delivered_orders(self, as_user, shopper, manager, products, give_back):
        response = as_user(shopper).post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": products[0].pk, "quantity": 1}],
                "payment_method": "cash",
                "address": ADDRESS,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="line-returns-0002",
        )
        order = Order.objects.get(number=response.json()["number"])

        refused = give_back(order, order.items.get(), 1)

        assert refused.status_code == 422
        assert refused.json()["code"] == "line_not_returnable"

    def test_cannot_return_more_than_what_is_left(self, delivered, give_back):
        phone_line, _ = lines_of(delivered)
        give_back(delivered, phone_line, 1)

        refused = give_back(delivered, phone_line, 2)

        assert refused.status_code == 400
        assert refused.json()["code"] == "invalid_return_quantity"
        assert refused.json()["meta"]["remaining"] == 1

    def test_resellers_cannot_return_lines(self, delivered, give_back, reseller):
        phone_line, _ = lines_of(delivered)

        assert give_back(delivered, phone_line, 1, user=reseller).status_code == 403
        assert not OrderLineReturn.objects.exists()

    def test_a_failing_sales_update_rolls_the_return_back(
        self, delivered, give_back, products, monkeypatch
    ):
        phone, _ = products
        phone_line, _ = lines_of(delivered)
        monkeypatch.setattr(
            SalesFacade, "order_line_returned", Mock(side_effect=RuntimeError("boom"))
        )

        with pytest.raises(RuntimeError):
            give_back(delivered, phone_line, 1)

        assert not OrderLineReturn.objects.exists()
        assert stock_of(phone) == 8
        phone_line.refresh_from_db()
        assert phone_line.returned_quantity == 0

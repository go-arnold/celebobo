import random
from decimal import Decimal

import pytest

from apps.catalog.tests.factories import ProductFactory
from apps.orders.domain.pricing import line_amounts, spread
from apps.orders.facades import OrderAdjustmentFacade
from apps.orders.models import Coupon, Order
from apps.orders.tests.conftest import ADDRESS
from core.container import container
from core.domain.actor import Actor

D = Decimal


class TestSpread:
    def test_shares_follow_the_weights_and_add_up_to_the_cent(self):
        assert spread(D("10.00"), [D("10"), D("10"), D("10")]) == [D("3.34"), D("3.33"), D("3.33")]
        assert spread(D("15.00"), [D("120"), D("30")]) == [D("12.00"), D("3.00")]

    def test_nothing_to_spread(self):
        assert spread(D("0"), [D("5"), D("7")]) == [D("0.00"), D("0.00")]
        assert spread(D("4"), [D("0"), D("0")]) == [D("0.00"), D("0.00")]
        assert spread(D("4"), []) == []

    def test_many_random_cases_stay_exact_and_never_exceed_a_line(self):
        draw = random.Random(2026)  # noqa: S311 - reproducible test data
        for _ in range(500):
            weights = [D(draw.randint(1, 50_000)) / 100 for _ in range(draw.randint(1, 8))]
            amount = (sum(weights) * D(draw.random())).quantize(D("0.01"))

            shares = spread(amount, weights)

            assert sum(shares) == amount
            assert all(
                D(0) <= share <= weight for share, weight in zip(shares, weights, strict=True)
            )

    def test_points_is_spread_over_what_the_coupon_left(self):
        first, second = line_amounts([D("100"), D("50")], discount=D("50"), points=D("10"))

        assert (first.discount, second.discount) == (D("33.33"), D("16.67"))
        assert (first.points, second.points) == (D("6.67"), D("3.33"))
        assert (first.paid, second.paid) == (D("60.00"), D("30.00"))


pytestmark_db = pytest.mark.django_db


@pytest.fixture
def products(db):
    return (
        ProductFactory.create(price=D("10.00"), stock=10),
        ProductFactory.create(price=D("10.00"), stock=10),
        ProductFactory.create(price=D("10.00"), stock=10),
    )


def place(as_user, user, products, **extra) -> Order:
    response = as_user(user).post(
        "/api/v1/orders/",
        {
            "lines": [{"product_id": product.pk, "quantity": 1} for product in products],
            "payment_method": "cash",
            "address": ADDRESS,
            **extra,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="line-amounts-0001",
    )
    assert response.status_code == 201, response.json()
    return Order.objects.get(number=response.json()["number"])


def amounts(order: Order) -> list[tuple[Decimal, Decimal, Decimal]]:
    return [(item.discount, item.points, item.amount_paid) for item in order.items.all()]


@pytestmark_db
class TestCheckout:
    def test_the_coupon_is_spread_over_the_lines(self, as_user, shopper, products):
        Coupon.objects.create(code="DIX", kind="fixed", value=D("10.00"))

        order = place(as_user, shopper, products, coupon_code="DIX")

        assert order.discount == D("10.00")
        assert amounts(order) == [
            (D("3.34"), D("0.00"), D("6.66")),
            (D("3.33"), D("0.00"), D("6.67")),
            (D("3.33"), D("0.00"), D("6.67")),
        ]

    def test_without_coupon_each_line_is_paid_in_full(self, as_user, shopper, products):
        order = place(as_user, shopper, products)

        assert amounts(order) == [(D("0.00"), D("0.00"), D("10.00"))] * 3

    def test_order_details_show_the_line_amounts(self, as_user, shopper, products):
        Coupon.objects.create(code="DIX", kind="fixed", value=D("10.00"))
        order = place(as_user, shopper, products, coupon_code="DIX")

        lines = as_user(shopper).get(f"/api/v1/me/orders/{order.number}/").json()["items"]

        assert [(line["discount"], line["amount_paid"]) for line in lines] == [
            ("3.34", "6.66"),
            ("3.33", "6.67"),
            ("3.33", "6.67"),
        ]


@pytestmark_db
class TestRepricing:
    def test_a_new_price_spreads_the_coupon_again(
        self, as_user, shopper, manager, reseller, products
    ):
        Coupon.objects.create(code="DIX", kind="fixed", value=D("10.00"))
        order = place(as_user, shopper, products, coupon_code="DIX")
        as_user(manager).post(f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk})
        first = order.items.order_by("pk")[0]

        container.resolve(OrderAdjustmentFacade).apply(
            Actor.system(), order.pk, first.pk, D("5.00")
        )

        order.refresh_from_db()
        assert order.subtotal == D("25.00")
        assert amounts(order) == [
            (D("2.00"), D("0.00"), D("3.00")),
            (D("4.00"), D("0.00"), D("6.00")),
            (D("4.00"), D("0.00"), D("6.00")),
        ]
        paid = sum(item.amount_paid for item in order.items.all())
        assert paid == order.total - order.shipping_fee

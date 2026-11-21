"""Commission rules decided on 16 Nov 2026 (docs/business/05-sales-commissions.md)."""

from decimal import Decimal

import pytest
from django.db.models import F

from apps.catalog.models import Product
from apps.catalog.tests.factories import ProductFactory
from apps.orders.models import Coupon, Order, OrderItem
from apps.sales.models import CommissionEntry, Sale

pytestmark = pytest.mark.django_db

BO_ORDERS = "/api/v1/bo/orders/"
SALES = "/api/v1/bo/sales/"


def product(price="100.00", cost: str | None = "60.00", **fields) -> Product:
    return ProductFactory.create(
        price=Decimal(price),
        cost_price=None if cost is None else Decimal(cost),
        stock=20,
        **fields,
    )


def partner(price="50.00", gain="7.50") -> Product:
    return product(price, "45.00", origin="partner", partner_gain=Decimal(gain))


def entries(reseller) -> list[tuple[str, str, Decimal]]:
    return [
        (entry.kind, entry.rule, entry.amount)
        for entry in CommissionEntry.objects.filter(reseller=reseller).order_by("pk")
    ]


def net(reseller) -> Decimal:
    return sum(
        (entry.amount for entry in CommissionEntry.objects.filter(reseller=reseller)), Decimal(0)
    )


def deliver(as_user, manager, reseller, order_number: str) -> Order:
    order = Order.objects.get(number=order_number)
    api = as_user(manager)
    assert api.post(f"{BO_ORDERS}{order.pk}/assign/", {"reseller_id": reseller.pk}).status_code
    delivered = api.post(
        f"{BO_ORDERS}{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    assert delivered.status_code == 200, delivered.json()
    return order


def convert(api, order, key="rules-convert-01"):
    response = api.post(
        f"{BO_ORDERS}{order.pk}/convert-to-sales/", {}, format="json", HTTP_IDEMPOTENCY_KEY=key
    )
    assert response.status_code == 201, response.json()
    return response.json()


def edit(api, sale_id, price: str):
    response = api.patch(f"{SALES}{sale_id}/", {"unit_price": price}, format="json")
    assert response.status_code == 200, response.json()


class TestRecordedSales:
    def test_ten_percent_of_the_paid_amount(self, reseller, record_sale):
        record_sale(reseller, product(cost="60.00"), quantity=1, unit_price="100.00")

        assert entries(reseller) == [("earned", "paid", Decimal("10.00"))]

    def test_capped_at_half_the_margin(self, reseller, record_sale):
        # 2 x 100 paid, cost 2 x 92: margin 16 -> 8.00 instead of 20.00
        record_sale(reseller, product(cost="92.00"), quantity=2, unit_price="100.00")

        assert entries(reseller) == [("earned", "margin", Decimal("8.00"))]

    def test_negative_margin_earns_nothing(self, reseller, record_sale):
        body = record_sale(reseller, product(cost="110.00"), quantity=1, unit_price="100.00")

        assert entries(reseller) == []
        assert Sale.objects.get(pk=body["id"]).commissionable is True

    def test_unknown_cost_pays_ten_percent(self, reseller, record_sale):
        record_sale(reseller, product(cost=None), quantity=1, unit_price="45.00")

        assert entries(reseller) == [("earned", "unknown_cost", Decimal("4.50"))]

    def test_partner_products_follow_celebobo_gain(self, reseller, record_sale):
        # gain 2 x 7.50 = 15 -> 3.00, below 10 % of 100
        record_sale(reseller, partner(), quantity=2, unit_price="50.00")

        assert entries(reseller) == [("earned", "partner_gain", Decimal("3.00"))]

    def test_partner_products_never_pay_more_than_ten_percent(self, reseller, record_sale):
        # gain 12 -> 2.40, above 10 % of 20
        record_sale(reseller, partner("20.00", "12.00"), quantity=1, unit_price="20.00")

        assert entries(reseller) == [("earned", "paid", Decimal("2.00"))]

    def test_managers_record_for_a_reseller_with_the_same_rules(
        self, manager, reseller, record_sale
    ):
        record_sale(
            manager, product(cost="92.00"), quantity=1, unit_price="100.00", seller_id=reseller.pk
        )

        assert entries(reseller) == [("earned", "margin", Decimal("4.00"))]

    def test_no_commission_on_the_resellers_own_purchase(self, reseller, record_sale):
        body = record_sale(reseller, product(), quantity=1, buyer_id=reseller.pk)

        assert entries(reseller) == []
        assert Sale.objects.get(pk=body["id"]).commissionable is False

    def test_a_later_product_edit_changes_nothing(self, as_user, reseller, record_sale):
        item = partner()
        body = record_sale(reseller, item, quantity=1, unit_price="50.00")
        Product.objects.filter(pk=item.pk).update(
            origin="celebobo", partner_gain=None, cost_price=Decimal(1)
        )

        edit(as_user(reseller), body["id"], "40.00")

        # the snapshot still says partner, gain 7.50 -> 1.50
        assert entries(reseller)[-1] == ("earned", "partner_gain", Decimal("1.50"))


class TestEditing:
    def test_a_price_edit_recomputes_with_the_rules(self, as_user, reseller, record_sale):
        body = record_sale(reseller, product(cost="80.00"), quantity=1, unit_price="100.00")

        edit(as_user(reseller), body["id"], "90.00")

        assert entries(reseller) == [
            ("earned", "paid", Decimal("10.00")),
            ("reversed", "paid", Decimal("-10.00")),
            ("earned", "margin", Decimal("5.00")),
        ]
        assert net(reseller) == Decimal("5.00")

    def test_raising_a_price_above_the_cost_starts_earning(self, as_user, reseller, record_sale):
        body = record_sale(reseller, product(cost="100.00"), quantity=1, unit_price="95.00")

        edit(as_user(reseller), body["id"], "120.00")

        assert entries(reseller) == [("earned", "margin", Decimal("10.00"))]

    def test_lowering_a_price_below_the_cost_voids_it(self, as_user, reseller, record_sale):
        body = record_sale(reseller, product(cost="80.00"), quantity=1, unit_price="100.00")

        edit(as_user(reseller), body["id"], "70.00")

        assert net(reseller) == Decimal("0.00")

    def test_sales_without_commission_stay_without(self, as_user, reseller, record_sale):
        body = record_sale(reseller, product(), quantity=1, buyer_id=reseller.pk)

        edit(as_user(reseller), body["id"], "150.00")

        assert entries(reseller) == []


class TestRefunds:
    def test_reversal_is_proportional_to_the_refund(self, as_user, manager, reseller, record_sale):
        # margin 16 -> 8.00 earned; refunding a quarter of 200 reverses 2.00
        body = record_sale(reseller, product(cost="92.00"), quantity=2, unit_price="100.00")

        response = as_user(manager).post(
            f"{SALES}{body['id']}/refund/",
            {"kind": "refund", "amount": "50.00", "reason": "Geste commercial"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rules-refund-001",
        )

        assert response.status_code == 200, response.json()
        assert entries(reseller)[-1] == ("reversed", "margin", Decimal("-2.00"))
        assert net(reseller) == Decimal("6.00")

    def test_legacy_entries_are_reversed_from_what_they_earned(
        self, as_user, manager, reseller, record_sale
    ):
        body = record_sale(reseller, product(cost=None), quantity=1, unit_price="100.00")
        # an entry from the per-reseller rate days (7 %)
        CommissionEntry.objects.filter(reseller=reseller).update(
            rule="legacy_rate", amount=Decimal("7.00")
        )

        as_user(manager).post(
            f"{SALES}{body['id']}/refund/",
            {"kind": "refund", "amount": "50.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rules-refund-002",
        )

        assert entries(reseller)[-1] == ("reversed", "legacy_rate", Decimal("-3.50"))


class TestOrders:
    def test_a_real_money_order_earns_on_each_line(
        self, as_user, manager, reseller, shopper, place_order
    ):
        item = product("100.00", "92.00")
        order = deliver(
            as_user, manager, reseller, place_order(shopper, item, quantity=2)["number"]
        )

        convert(as_user(reseller), order)

        assert entries(reseller) == [("earned", "margin", Decimal("8.00"))]

    def test_points_cancel_the_whole_order(self, as_user, manager, reseller, shopper, place_order):
        order = deliver(
            as_user, manager, reseller, place_order(shopper, product(), quantity=1)["number"]
        )
        # 5 $ of the order paid with points (spread on its only line)
        Order.objects.filter(pk=order.pk).update(points=Decimal(5), total=F("total") - 5)
        OrderItem.objects.filter(order=order).update(
            points=Decimal(5), amount_paid=F("amount_paid") - 5
        )

        sales = convert(as_user(reseller), order)

        assert sales
        assert entries(reseller) == []
        assert not Sale.objects.filter(commissionable=True).exists()

    def test_a_coupon_cancels_the_whole_order(
        self, as_user, manager, reseller, shopper, place_order
    ):
        Coupon.objects.create(code="BIENVENUE10", kind="percent", value=Decimal(10))
        number = place_order(shopper, product(), quantity=1, coupon_code="BIENVENUE10")["number"]
        order = deliver(as_user, manager, reseller, number)
        assert order.discount > 0

        convert(as_user(reseller), order)

        assert entries(reseller) == []

    def test_sale_prices_are_real_money(self, as_user, manager, reseller, shopper, place_order):
        item = product("120.00", "60.00")
        item.sale_price = Decimal("100.00")
        item.save(update_fields=["sale_price"])
        order = deliver(as_user, manager, reseller, place_order(shopper, item)["number"])

        convert(as_user(reseller), order)

        assert entries(reseller) == [("earned", "paid", Decimal("10.00"))]

    def test_no_commission_on_the_resellers_own_order(
        self, as_user, manager, reseller, place_order
    ):
        order = deliver(
            as_user, manager, reseller, place_order(reseller, product(), quantity=1)["number"]
        )

        convert(as_user(reseller), order)

        assert entries(reseller) == []

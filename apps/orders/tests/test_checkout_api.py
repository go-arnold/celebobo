from decimal import Decimal

import pytest

from apps.accounts.tests.factories import AddressFactory, UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.orders.domain.events import OrderPlaced
from apps.orders.models import Cart, Order
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"


def payload(product, quantity=1, **overrides):
    return {
        "lines": [{"product_id": product.pk, "quantity": quantity}],
        "payment_method": "cash",
        "address": ADDRESS,
        **overrides,
    }


class TestQuote:
    def test_quote_applies_shipping_rules(self, api, phone):
        cheap = api.post(
            "/api/v1/checkout/quote/", {"lines": [{"product_id": phone.pk, "quantity": 1}]}
        )
        free = api.post(
            "/api/v1/checkout/quote/", {"lines": [{"product_id": phone.pk, "quantity": 2}]}
        )

        assert cheap.json()["shipping_fee"] == "2.98"
        assert cheap.json()["free_shipping_remaining"] == "79.00"
        assert free.json()["shipping_fee"] == "0.00"
        assert free.json()["total"] == "240.00"

    def test_quantity_limit(self, api, phone):
        response = api.post(
            "/api/v1/checkout/quote/", {"lines": [{"product_id": phone.pk, "quantity": 11}]}
        )

        assert response.status_code == 400


class TestPlaceOrder:
    def test_creates_order_reserves_stock_and_publishes(
        self, as_user, shopper, phone, published_events
    ):
        response = as_user(shopper).post(
            ORDERS, payload(phone, 2, note="Appeler avant"), HTTP_IDEMPOTENCY_KEY="place-0001"
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "pending"
        assert body["number"].startswith("CB-")
        assert body["total"] == "240.00"
        assert body["items"][0]["name"] == "Galaxy A55"
        assert body["address"]["quarter"] == "Gombe"
        assert body["allowed_transitions"] == []
        assert "client" not in body
        assert [entry["status"] for entry in body["history"]] == ["pending"]
        phone.refresh_from_db()
        assert phone.stock == 3
        assert published_events.single(OrderPlaced).number == body["number"]

    def test_uses_the_address_book(self, as_user, shopper, phone):
        address = AddressFactory.create(user=shopper, quarter="Limete")

        body = (
            as_user(shopper)
            .post(
                ORDERS,
                payload(phone, address=None, address_id=address.pk),
                HTTP_IDEMPOTENCY_KEY="place-0002",
            )
            .json()
        )

        assert body["address"]["quarter"] == "Limete"

    def test_foreign_address_is_not_found(self, as_user, shopper, phone):
        foreign = AddressFactory.create(user=UserFactory.create())

        response = as_user(shopper).post(
            ORDERS,
            payload(phone, address=None, address_id=foreign.pk),
            HTTP_IDEMPOTENCY_KEY="place-0003",
        )

        assert response.status_code == 404

    def test_address_is_required(self, as_user, shopper, phone):
        response = as_user(shopper).post(
            ORDERS, payload(phone, address=None), HTTP_IDEMPOTENCY_KEY="place-0004"
        )

        assert response.json()["code"] == "address_required"

    def test_insufficient_stock_rolls_everything_back(self, as_user, shopper, phone):
        other = ProductFactory.create(stock=1)
        body = {
            **payload(phone),
            "lines": [
                {"product_id": phone.pk, "quantity": 1},
                {"product_id": other.pk, "quantity": 2},
            ],
        }

        response = as_user(shopper).post(ORDERS, body, HTTP_IDEMPOTENCY_KEY="place-0005")

        assert response.status_code == 422
        assert response.json()["code"] == "insufficient_stock"
        assert not Order.objects.exists()
        phone.refresh_from_db()
        assert phone.stock == 5

    def test_idempotent_retries_do_not_duplicate(self, as_user, shopper, phone):
        api = as_user(shopper)

        first = api.post(ORDERS, payload(phone), HTTP_IDEMPOTENCY_KEY="place-0006")
        retry = api.post(ORDERS, payload(phone), HTTP_IDEMPOTENCY_KEY="place-0006")

        assert retry.json()["number"] == first.json()["number"]
        assert retry["Idempotent-Replayed"] == "true"
        assert Order.objects.count() == 1

    def test_clears_the_server_cart(self, as_user, shopper, phone):
        api = as_user(shopper)
        api.post("/api/v1/cart/items/", {"product_id": phone.pk, "quantity": 1})

        api.post(ORDERS, payload(phone), HTTP_IDEMPOTENCY_KEY="place-0007")

        assert not Cart.objects.get(user=shopper).items.exists()

    def test_requires_authentication_and_items(self, api, as_user, shopper, phone):
        assert (
            api.post(ORDERS, payload(phone), HTTP_IDEMPOTENCY_KEY="place-0008").status_code == 401
        )
        empty = as_user(shopper).post(
            ORDERS, {**payload(phone), "lines": []}, HTTP_IDEMPOTENCY_KEY="place-0009"
        )
        assert empty.status_code == 400

    def test_sale_price_is_charged(self, as_user, shopper):
        product = ProductFactory.create(price=Decimal(300), sale_price=Decimal(250))

        body = (
            as_user(shopper)
            .post(ORDERS, payload(product), HTTP_IDEMPOTENCY_KEY="place-0010")
            .json()
        )

        assert body["items"][0]["unit_price"] == "250.00"
        assert body["shipping_fee"] == "0.00"

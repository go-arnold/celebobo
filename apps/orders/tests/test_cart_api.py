import pytest

from apps.catalog.models import Product
from apps.catalog.tests.factories import VariantFactory
from apps.orders.models import Cart

pytestmark = pytest.mark.django_db

ITEMS = "/api/v1/cart/items/"


class TestGuestCart:
    def test_guest_gets_a_token_and_keeps_adding(self, api, phone):
        first = api.post(ITEMS, {"product_id": phone.pk, "quantity": 1})
        token = first.json()["token"]
        second = api.post(ITEMS, {"product_id": phone.pk, "quantity": 2}, HTTP_X_CART_TOKEN=token)

        assert first.status_code == 201
        assert second.json()["lines"][0]["quantity"] == 3
        assert second.json()["quote"]["subtotal"] == "360.00"

    def test_update_and_remove(self, api, phone):
        token = api.post(ITEMS, {"product_id": phone.pk, "quantity": 1}).json()["token"]
        cart = api.get("/api/v1/cart/", HTTP_X_CART_TOKEN=token).json()
        item_id = cart["lines"][0]["id"]

        updated = api.patch(f"{ITEMS}{item_id}/", {"quantity": 4}, HTTP_X_CART_TOKEN=token)
        removed = api.delete(f"{ITEMS}{item_id}/", HTTP_X_CART_TOKEN=token)

        assert updated.json()["lines"][0]["quantity"] == 4
        assert removed.json()["lines"] == []

    def test_unavailable_lines_are_flagged_and_excluded(self, api, phone):
        token = api.post(ITEMS, {"product_id": phone.pk, "quantity": 1}).json()["token"]
        Product.objects.filter(pk=phone.pk).update(is_active=False)

        cart = api.get("/api/v1/cart/", HTTP_X_CART_TOKEN=token).json()

        assert cart["lines"][0]["available"] is False
        assert cart["quote"]["subtotal"] == "0.00"

    def test_variant_is_required(self, api):
        variant = VariantFactory.create()

        response = api.post(ITEMS, {"product_id": variant.product_id, "quantity": 1})

        assert response.status_code == 422
        assert response.json()["code"] == "variant_required"

    def test_invalid_token(self, api):
        response = api.get("/api/v1/cart/", HTTP_X_CART_TOKEN="nope")

        assert response.status_code == 400

    def test_unknown_item(self, api):
        assert api.delete(f"{ITEMS}999/").json()["code"] == "cart_line_not_found"


class TestUserCart:
    def test_merge_guest_cart_at_login(self, api, as_user, shopper, phone):
        token = api.post(ITEMS, {"product_id": phone.pk, "quantity": 2}).json()["token"]
        user_api = as_user(shopper)
        user_api.post(ITEMS, {"product_id": phone.pk, "quantity": 1})

        merged = user_api.post("/api/v1/cart/merge/", {"token": token})

        assert merged.json()["token"] is None
        assert merged.json()["lines"][0]["quantity"] == 3
        assert not Cart.objects.filter(user__isnull=True).exists()

    def test_quantities_are_capped(self, as_user, shopper, phone):
        api = as_user(shopper)
        api.post(ITEMS, {"product_id": phone.pk, "quantity": 8})

        cart = api.post(ITEMS, {"product_id": phone.pk, "quantity": 8}).json()

        assert cart["lines"][0]["quantity"] == 10

    def test_clear(self, as_user, shopper, phone):
        api = as_user(shopper)
        api.post(ITEMS, {"product_id": phone.pk, "quantity": 1})

        assert api.delete("/api/v1/cart/").status_code == 204
        assert api.get("/api/v1/cart/").json()["lines"] == []

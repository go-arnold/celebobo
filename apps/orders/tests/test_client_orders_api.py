import pytest

from apps.accounts.tests.factories import UserFactory
from apps.catalog.domain.events import ProductChanged
from apps.orders.domain.events import OrderStatusChanged
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/orders/"


class TestMyOrders:
    def test_lists_only_my_orders(self, as_user, shopper, phone, place_order):
        mine = place_order(shopper, phone)
        place_order(UserFactory.create(), phone)

        body = as_user(shopper).get(MINE).json()

        assert body["meta"]["count"] == 1
        assert body["results"][0]["number"] == mine["number"]
        assert body["results"][0]["preview_name"] == "Galaxy A55"
        assert body["results"][0]["items_count"] == 1

    def test_status_filter(self, as_user, shopper, phone, place_order):
        place_order(shopper, phone)

        assert as_user(shopper).get(MINE, {"status": "delivered"}).json()["meta"]["count"] == 0

    def test_detail_by_number_is_case_insensitive(self, as_user, shopper, phone, place_order):
        number = place_order(shopper, phone)["number"]

        body = as_user(shopper).get(f"{MINE}{number.lower()}/").json()

        assert body["number"] == number
        assert body["allowed_transitions"] == ["cancelled"]

    def test_other_clients_orders_are_not_found(self, as_user, shopper, phone, place_order):
        number = place_order(UserFactory.create(), phone)["number"]

        response = as_user(shopper).get(f"{MINE}{number}/")

        assert response.status_code == 404
        assert response.json()["code"] == "order_not_found"


class TestCancellation:
    def test_pending_orders_can_be_cancelled_and_restock(
        self, as_user, shopper, phone, place_order, published_events
    ):
        number = place_order(shopper, phone, quantity=2)["number"]

        response = as_user(shopper).post(
            f"{MINE}{number}/cancel/", {"reason": "changed_mind", "details": "  Trop cher  "}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
        assert response.json()["cancel_reason"] == "changed_mind"
        phone.refresh_from_db()
        assert phone.stock == 5
        change = published_events.single(OrderStatusChanged)
        assert (change.previous_status, change.status) == ("pending", "cancelled")
        assert published_events.of_type(ProductChanged)

    def test_assigned_orders_cannot_be_cancelled_by_the_client(
        self, as_user, shopper, phone, place_order
    ):
        number = place_order(shopper, phone)["number"]
        Order.objects.filter(number=number).update(status="assigned")

        response = as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "too_slow"})

        assert response.status_code == 422
        assert response.json()["code"] == "invalid_transition"


class TestTracking:
    url = "/api/v1/orders/track/"

    @pytest.mark.parametrize("contact", ["ALINE@celebobo.test", "+243 81 234 5678"])
    def test_tracks_with_email_or_delivery_phone(self, api, shopper, phone, place_order, contact):
        number = place_order(shopper, phone)["number"]

        body = api.post(self.url, {"number": number, "contact": contact}).json()

        assert body["status"] == "pending"
        assert body["items"] == [{"name": "Galaxy A55", "variant_label": "", "quantity": 1}]
        assert [entry["status"] for entry in body["history"]] == ["pending"]
        assert "actor_name" not in str(body)

    def test_wrong_contact_looks_like_unknown_order(self, api, shopper, phone, place_order):
        number = place_order(shopper, phone)["number"]

        response = api.post(self.url, {"number": number, "contact": "x@celebobo.test"})

        assert response.status_code == 404
        assert response.json()["code"] == "order_not_found"

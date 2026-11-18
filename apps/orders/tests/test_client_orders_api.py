import pytest

from apps.accounts.tests.factories import UserFactory
from apps.catalog.domain.events import ProductChanged
from apps.orders.domain.events import OrderRefunded, OrderStatusChanged, RefundDue
from apps.orders.models import Order

pytestmark = pytest.mark.django_db

MINE = "/api/v1/me/orders/"
BO = "/api/v1/bo/orders/"


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

    @pytest.mark.parametrize("status", ["assigned", "confirmed"])
    def test_the_client_cancels_until_payment_without_refund(
        self, as_user, shopper, phone, place_order, *, status, published_events
    ):
        number = place_order(shopper, phone)["number"]
        Order.objects.filter(number=number).update(status=status)

        response = as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "too_slow"})

        assert response.status_code == 200, response.json()
        assert (response.json()["status"], response.json()["refund_due"]) == ("cancelled", "0.00")
        assert not published_events.of_type(RefundDue)

    def test_a_paid_order_cancelled_by_the_client_is_owed_back(
        self, as_user, shopper, phone, place_order, published_events
    ):
        number = place_order(shopper, phone)["number"]
        Order.objects.filter(number=number).update(status="paid")

        body = as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "changed_mind"}).json()

        order = Order.objects.get(number=number)
        assert body["status"] == "cancelled"
        assert order.refund_due == order.total
        assert (body["refund_due"], body["refunded_at"]) == (str(order.total), None)
        assert published_events.single(RefundDue).amount == order.total
        phone.refresh_from_db()
        assert phone.stock == 5

    def test_out_for_delivery_the_client_can_no_longer_cancel(
        self, as_user, shopper, phone, place_order
    ):
        number = place_order(shopper, phone)["number"]
        Order.objects.filter(number=number).update(status="shipping")

        response = as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "too_slow"})
        detail = as_user(shopper).get(f"{MINE}{number}/").json()

        assert response.json()["code"] == "invalid_transition"
        assert detail["allowed_transitions"] == []


class TestRefunds:
    @pytest.fixture
    def owed(self, as_user, shopper, phone, place_order) -> Order:
        number = place_order(shopper, phone)["number"]
        Order.objects.filter(number=number).update(status="paid")
        as_user(shopper).post(f"{MINE}{number}/cancel/", {"reason": "changed_mind"})
        return Order.objects.get(number=number)

    def test_staff_see_and_record_the_refund(self, as_user, manager, owed, published_events):
        staff = as_user(manager)
        listed = staff.get(BO, {"status": "refund_pending"}).json()

        recorded = staff.post(f"{BO}{owed.pk}/refund/", {"note": " MP-4821 "})
        again = staff.post(f"{BO}{owed.pk}/refund/", {})

        assert [row["number"] for row in listed["results"]] == [owed.number]
        assert listed["results"][0]["refund_status"] == "due"
        assert listed["meta"]["counts"]["refund_pending"] == 1
        assert recorded.status_code == 200, recorded.json()
        assert recorded.json()["refunded_at"] is not None
        assert recorded.json()["refund_note"] == "MP-4821"
        assert recorded.json()["history"][-1]["note"] == (
            f"Remboursement de {owed.total} $ effectué — MP-4821"
        )
        assert published_events.single(OrderRefunded).amount == owed.total
        assert again.json()["code"] == "no_refund_due"
        assert staff.get(BO, {"status": "refund_pending"}).json()["meta"]["count"] == 0

    def test_staff_cancelling_an_order_out_for_delivery_owe_it_back(
        self, as_user, manager, shopper, phone, place_order
    ):
        number = place_order(shopper, phone)["number"]
        order = Order.objects.get(number=number)
        Order.objects.filter(pk=order.pk).update(status="shipping")

        as_user(manager).post(f"{BO}{order.pk}/transition/", {"to": "cancelled"})

        order.refresh_from_db()
        assert (order.status, order.refund_due) == ("cancelled", order.total)

    def test_only_staff_record_refunds(self, as_user, reseller, owed):
        Order.objects.filter(pk=owed.pk).update(assigned_reseller=reseller)

        assert as_user(reseller).post(f"{BO}{owed.pk}/refund/", {}).status_code == 403

    def test_an_order_without_payment_has_nothing_to_refund(
        self, as_user, manager, shopper, phone, place_order
    ):
        number = place_order(shopper, phone)["number"]
        order = Order.objects.get(number=number)

        response = as_user(manager).post(f"{BO}{order.pk}/refund/", {})

        assert response.json()["code"] == "no_refund_due"


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

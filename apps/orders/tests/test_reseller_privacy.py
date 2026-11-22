from datetime import timedelta
from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.domain.contact import reseller_contact_hidden
from apps.orders.domain.enums import OrderStatus
from apps.orders.models import Order, OrderStatusEvent

pytestmark = pytest.mark.django_db

BO = "/api/v1/bo/orders/"


@pytest.fixture
def placed(shopper, phone, place_order) -> Order:
    return Order.objects.get(number=place_order(shopper, phone)["number"])


@pytest.fixture
def order(as_user, manager, reseller, placed: Order, django_capture_on_commit_callbacks) -> Order:
    # the reseller joins the order thread in an after-commit handler
    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).post(f"{BO}{placed.pk}/assign/", {"reseller_id": reseller.pk})
    return placed


class TestOrderDetail:
    def test_resellers_do_not_get_the_client_email(self, as_user, reseller, order):
        client = as_user(reseller).get(f"{BO}{order.pk}/").json()["client"]

        assert client["email"] is None
        assert client["name"] == "Aline Mbuyi"
        assert client["phone"] == "+243 81 000 0001"

    def test_staff_still_see_it(self, as_user, manager, order):
        staff_view = as_user(manager).get(f"{BO}{order.pk}/").json()["client"]

        assert staff_view["email"] == "aline@celebobo.test"

    def test_a_nameless_client_shows_the_recipient_to_resellers(
        self, as_user, manager, reseller, order
    ):
        User.objects.filter(pk=order.client_id).update(first_name="", last_name="")

        reseller_view = as_user(reseller).get(f"{BO}{order.pk}/").json()
        listed = as_user(reseller).get(BO).json()["results"][0]
        staff_view = as_user(manager).get(f"{BO}{order.pk}/").json()

        assert reseller_view["client"]["name"] == "Aline Mbuyi"
        assert listed["client_name"] == "Aline Mbuyi"
        assert staff_view["client"]["name"] == "aline@celebobo.test"


class TestSearch:
    def test_resellers_cannot_search_orders_by_client_email(
        self, as_user, manager, reseller, order
    ):
        by_email = as_user(reseller).get(BO, {"search": "aline@celebobo"}).json()
        by_name = as_user(reseller).get(BO, {"search": "Mbuyi"}).json()
        staff = as_user(manager).get(BO, {"search": "aline@celebobo"}).json()

        assert by_email["meta"]["count"] == 0
        assert by_name["meta"]["count"] == 1
        assert staff["meta"]["count"] == 1

    def test_resellers_cannot_search_conversations_by_client_email(
        self, as_user, manager, reseller, order
    ):
        def found(user, term):
            return as_user(user).get("/api/v1/conversations/", {"search": term}).json()

        assert found(reseller, "aline@celebobo")["meta"]["count"] == 0
        assert found(reseller, order.number)["meta"]["count"] == 1
        assert found(manager, "aline@celebobo")["meta"]["count"] == 1


SALES_CONVERTIBLE = "/api/v1/bo/orders/convertible/"
ADDRESS_PHONE = "+243 81 234 5678"


def deliver(as_user, manager, order: Order, *, days_ago: float) -> None:
    response = as_user(manager).post(
        f"{BO}{order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
    )
    assert response.status_code == 200, response.json()
    OrderStatusEvent.objects.filter(order=order, to_status=OrderStatus.DELIVERED.value).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


@pytest.fixture
def noted(order: Order) -> Order:
    Order.objects.filter(pk=order.pk).update(note="Portail bleu, appeler le +243 99 000 0000")
    return order


def assert_visible(body: dict[str, Any]) -> None:
    assert body["contact_hidden"] is False
    assert body["address"]["phone"] == ADDRESS_PHONE
    assert body["address"]["line1"] == "Av. Lumumba n°12"
    assert body["address"]["quarter"] == "Ibanda"
    assert body["note"].startswith("Portail bleu")
    assert body["client"]["phone"] == "+243 81 000 0001"


def assert_hidden(body: dict[str, Any]) -> None:
    assert body["contact_hidden"] is True
    assert body["address"] == {
        "recipient": "Aline Mbuyi",
        "phone": "",
        "line1": "",
        "quarter": "",
        "city": "Bukavu",
        "country": "RD Congo",
    }
    assert body["note"] == ""
    assert body["client"]["phone"] is None
    # the name stays: the reseller keeps their sales and ratings
    assert body["client"]["name"] == "Aline Mbuyi"


class TestContactWindowRule:
    NOW = timezone.now()

    @pytest.mark.parametrize(
        "status",
        [OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.PAID, OrderStatus.SHIPPING],
    )
    def test_open_orders_keep_the_contact_whatever_their_age(self, status):
        assert reseller_contact_hidden(status, None, now=self.NOW) is False

    @pytest.mark.parametrize("status", [OrderStatus.DELIVERED, OrderStatus.RETURNED])
    def test_seven_days_after_delivery(self, status):
        def hidden(days: float) -> bool:
            return reseller_contact_hidden(status, self.NOW - timedelta(days=days), now=self.NOW)

        assert hidden(0) is False
        assert hidden(6.9) is False
        assert hidden(7) is True
        assert hidden(30) is True

    def test_cancelled_orders_hide_it_at_once(self):
        assert reseller_contact_hidden(OrderStatus.CANCELLED, None, now=self.NOW) is True

    def test_a_delivery_without_its_date_fails_closed(self):
        assert reseller_contact_hidden(OrderStatus.DELIVERED, None, now=self.NOW) is True


class TestContactWindow:
    def test_before_delivery_the_reseller_sees_the_contact(self, as_user, reseller, noted):
        assert_visible(as_user(reseller).get(f"{BO}{noted.pk}/").json())

    def test_during_the_seven_days_nothing_changes(self, as_user, manager, reseller, noted):
        deliver(as_user, manager, noted, days_ago=6.5)

        assert_visible(as_user(reseller).get(f"{BO}{noted.pk}/").json())

    def test_seven_days_after_delivery_the_reseller_loses_it(
        self, as_user, manager, reseller, noted
    ):
        deliver(as_user, manager, noted, days_ago=7.1)

        assert_hidden(as_user(reseller).get(f"{BO}{noted.pk}/").json())

    def test_staff_keep_it(self, as_user, manager, noted):
        deliver(as_user, manager, noted, days_ago=30)

        assert_visible(as_user(manager).get(f"{BO}{noted.pk}/").json())

    def test_the_client_keeps_it_on_their_own_order(self, as_user, manager, shopper, noted):
        deliver(as_user, manager, noted, days_ago=30)

        body = as_user(shopper).get(f"/api/v1/me/orders/{noted.number}/").json()

        assert body["address"]["phone"] == ADDRESS_PHONE
        assert "contact_hidden" not in body

    def test_returned_orders_follow_the_delivery_date(self, as_user, manager, reseller, noted):
        deliver(as_user, manager, noted, days_ago=8)
        Order.objects.filter(pk=noted.pk).update(status=OrderStatus.RETURNED.value)

        assert_hidden(as_user(reseller).get(f"{BO}{noted.pk}/").json())

    def test_cancelled_orders_hide_it_at_once(self, as_user, shopper, reseller, noted):
        cancelled = as_user(shopper).post(
            f"/api/v1/me/orders/{noted.number}/cancel/", {"reason": "changed_mind"}
        )
        assert cancelled.status_code == 200

        assert_hidden(as_user(reseller).get(f"{BO}{noted.pk}/").json())

    def test_the_data_stays_on_the_order(self, as_user, manager, noted):
        deliver(as_user, manager, noted, days_ago=30)

        noted.refresh_from_db()
        assert noted.phone == ADDRESS_PHONE
        assert noted.line1 == "Av. Lumumba n°12"

    def test_hiding_adds_no_query(self, as_user, manager, reseller, noted):
        deliver(as_user, manager, noted, days_ago=1)
        api = as_user(reseller)
        with CaptureQueriesContext(connection) as visible:
            api.get(f"{BO}{noted.pk}/")
        OrderStatusEvent.objects.filter(order=noted, to_status="delivered").update(
            created_at=timezone.now() - timedelta(days=10)
        )
        with CaptureQueriesContext(connection) as hidden:
            body = api.get(f"{BO}{noted.pk}/").json()

        assert body["contact_hidden"] is True
        assert len(hidden) == len(visible)


class TestSearchByPhone:
    def found(self, api, term: str) -> int:
        count: int = api.get(BO, {"search": term}).json()["meta"]["count"]
        return count

    def test_within_the_window_the_reseller_finds_the_order_by_phone(
        self, as_user, manager, reseller, order
    ):
        deliver(as_user, manager, order, days_ago=2)

        assert self.found(as_user(reseller), "234 5678") == 1

    def test_after_it_the_phone_no_longer_finds_it(self, as_user, manager, reseller, order):
        deliver(as_user, manager, order, days_ago=8)

        assert self.found(as_user(reseller), "234 5678") == 0
        assert self.found(as_user(reseller), "Mbuyi") == 1
        assert self.found(as_user(manager), "234 5678") == 1

    def test_nor_on_a_cancelled_order(self, as_user, shopper, reseller, order):
        as_user(shopper).post(f"/api/v1/me/orders/{order.number}/cancel/", {"reason": "other"})

        assert self.found(as_user(reseller), "234 5678") == 0

    def test_before_delivery_it_does(self, as_user, reseller, order):
        assert self.found(as_user(reseller), "234 5678") == 1

    def test_the_sales_conversion_search_follows_the_same_rule(
        self, as_user, manager, reseller, order
    ):
        deliver(as_user, manager, order, days_ago=8)

        def found(user, term):
            return as_user(user).get(SALES_CONVERTIBLE, {"search": term}).json()

        assert found(reseller, "234 5678") == []
        assert [row["id"] for row in found(reseller, "Mbuyi")] == [order.pk]
        assert [row["id"] for row in found(manager, "234 5678")] == [order.pk]

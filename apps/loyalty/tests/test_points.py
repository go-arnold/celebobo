from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import (
    AdminFactory,
    ManagerFactory,
    ResellerFactory,
    UserFactory,
)
from apps.catalog.tests.factories import ProductFactory
from apps.loyalty.facades import PointsFacade
from apps.loyalty.handlers import settle_points
from apps.loyalty.models import LoyaltySettings, PointsEntry
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from apps.orders.models import Order
from core.container import container

pytestmark = pytest.mark.django_db

ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Ibanda",
    "city": "Bukavu",
    "country": "RD Congo",
}


@pytest.fixture
def programme():
    LoyaltySettings.objects.update_or_create(pk=1, defaults={"points_enabled": True})


@pytest.fixture
def client_user():
    return UserFactory.create()


@pytest.fixture
def product():
    return ProductFactory.create(price=Decimal("100.00"), stock=20)


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def credit(user, amount, *, available_in=-1):
    return PointsEntry.objects.create(
        user=user,
        kind="earn",
        amount=Decimal(amount),
        remaining=Decimal(amount),
        available_at=timezone.now() + timedelta(days=available_in),
    )


def lines(product, quantity=1):
    return [{"product_id": product.pk, "quantity": quantity}]


def place(user, product, *, points="0", key="checkout-0001", expect=201):
    response = as_api(user).post(
        "/api/v1/orders/",
        {"lines": lines(product), "payment_method": "cash", "address": ADDRESS, "points": points},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == expect, response.json()
    return response.json()


def status_changed(order_id, status):
    order = Order.objects.get(pk=order_id)
    settle_points(
        OrderStatusChanged(
            order_id=order.pk,
            client_id=order.client_id,
            reseller_id=None,
            previous_status=OrderStatus.SHIPPING,
            status=status,
        )
    )


def balance(user):
    return as_api(user).get("/api/v1/me/points/").json()


class TestEarning:
    def test_every_client_earns_one_percent_after_the_return_period(
        self, programme, client_user, product
    ):
        order = place(client_user, product)

        status_changed(order["id"], OrderStatus.DELIVERED)

        entry = PointsEntry.objects.get(kind="earn")
        assert entry.amount == Decimal("1.00")
        assert timedelta(days=6) < entry.available_at - timezone.now() <= timedelta(days=7)
        mine = balance(client_user)
        assert (mine["eligible"], mine["available"], mine["pending"]) == (True, "0.00", "1.00")
        assert mine["history"][0] | {"at": None} == {
            "kind": "earn",
            "amount": "1.00",
            "at": None,
            "order_number": order["number"],
            "pending": True,
        }
        detail = as_api(client_user).get(f"/api/v1/me/orders/{order['number']}/").json()
        assert detail["points_earned"] == "1.00"

    def test_delivering_twice_earns_once(self, programme, client_user, product):
        order = place(client_user, product)

        status_changed(order["id"], OrderStatus.DELIVERED)
        status_changed(order["id"], OrderStatus.DELIVERED)

        assert PointsEntry.objects.filter(kind="earn").count() == 1

    def test_a_returned_order_loses_its_points(self, programme, client_user, product):
        order = place(client_user, product)
        status_changed(order["id"], OrderStatus.DELIVERED)

        status_changed(order["id"], OrderStatus.RETURNED)

        assert balance(client_user)["pending"] == "0.00"
        detail = as_api(client_user).get(f"/api/v1/me/orders/{order['number']}/").json()
        assert detail["points_earned"] is None

    def test_nothing_while_the_programme_is_off(self, client_user, product):
        order = place(client_user, product)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert not PointsEntry.objects.exists()
        assert balance(client_user)["eligible"] is False


class TestSpending:
    def quote(self, user, product, points="0"):
        return (
            as_api(user)
            .post(
                "/api/v1/checkout/quote/",
                {"lines": lines(product), "city": "Bukavu", "points": points},
                format="json",
            )
            .json()
        )

    def test_the_client_chooses_how_many_points_to_use(self, programme, client_user, product):
        credit(client_user, "80.00")

        offered = self.quote(client_user, product)
        used = self.quote(client_user, product, points="30")

        assert (offered["points_available"], offered["points"]) == ("80.00", "0.00")
        assert used["points"] == "30.00"
        assert Decimal(used["total"]) == Decimal(offered["total"]) - Decimal(30)

    def test_no_cap_but_the_items_price(self, programme, client_user, product):
        credit(client_user, "150.00")

        quote = self.quote(client_user, product, points="150")

        # points never pay the delivery: at most the items' price
        assert (quote["points_available"], quote["points"]) == ("100.00", "100.00")

    def test_even_a_few_cents_can_be_used(self, programme, client_user, product):
        credit(client_user, "0.09")

        assert self.quote(client_user, product, points="0.09")["points"] == "0.09"

    def test_pending_points_cannot_be_spent(self, programme, client_user, product):
        credit(client_user, "20.00", available_in=3)

        assert self.quote(client_user, product, points="20")["points"] == "0.00"

    def test_ordering_uses_the_oldest_points_first(self, programme, client_user, product):
        newer = credit(client_user, "40.00", available_in=-1)
        older = credit(client_user, "30.00", available_in=-30)

        order = place(client_user, product, points="50")

        saved = Order.objects.get(pk=order["id"])
        assert saved.points == Decimal("50.00")
        line = saved.items.get()
        assert (line.points, line.amount_paid) == (Decimal("50.00"), Decimal("50.00"))
        newer.refresh_from_db()
        older.refresh_from_db()
        assert (older.remaining, newer.remaining) == (Decimal("0.00"), Decimal("20.00"))
        assert balance(client_user)["available"] == "20.00"

    def test_asking_for_more_than_the_balance_is_refused(self, programme, client_user, product):
        credit(client_user, "10.00")

        response = place(client_user, product, points="25", expect=409)

        assert response["code"] == "points_unavailable"

    def test_cancelling_gives_the_points_back(self, programme, client_user, product):
        credit(client_user, "60.00")
        order = place(client_user, product, points="60")

        status_changed(order["id"], OrderStatus.CANCELLED)

        assert balance(client_user)["available"] == "60.00"

    def test_points_used_earn_nothing(self, programme, client_user, product):
        credit(client_user, "60.00")
        order = place(client_user, product, points="60")

        status_changed(order["id"], OrderStatus.DELIVERED)

        # 1 % of the 40 $ really paid
        assert PointsEntry.objects.get(order_id=order["id"], kind="earn").amount == Decimal("0.40")

    def test_nothing_when_the_programme_is_off(self, client_user, product):
        credit(client_user, "60.00")

        assert self.quote(client_user, product, points="60")["points"] == "0.00"


class TestClosing:
    """Switched off, the programme lets clients use their points for 3 more months."""

    def switch(self, enabled):
        api = APIClient()
        api.force_authenticate(AdminFactory.create())
        response = api.patch(
            "/api/v1/bo/loyalty/settings/", {"points_enabled": enabled}, format="json"
        )
        assert response.status_code == 200, response.json()

    def test_points_stay_usable_for_three_months(self, programme, client_user, product):
        credit(client_user, "40.00")

        self.switch(False)

        mine = balance(client_user)
        assert mine["eligible"] is True
        assert mine["closes_at"] is not None
        order = place(client_user, product, points="40")
        assert order["points"] == "40.00"

    def test_nothing_is_earned_once_switched_off(self, programme, client_user, product):
        order = place(client_user, product)
        self.switch(False)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert not PointsEntry.objects.filter(kind="earn").exists()

    def test_after_three_months_the_points_cannot_be_used(self, programme, client_user, product):
        credit(client_user, "40.00")
        self.switch(False)
        LoyaltySettings.objects.filter(pk=1).update(
            points_disabled_at=timezone.now() - timedelta(days=93)
        )

        mine = balance(client_user)
        assert (mine["eligible"], mine["closes_at"]) == (False, None)
        place(client_user, product, points="40", expect=409)

    def test_the_invoice_promises_nothing_once_switched_off(self, programme, client_user, product):
        credit(client_user, "5.00")
        order = place(client_user, product)
        self.switch(False)

        statement = container.resolve(PointsFacade).invoice_statement(client_user.pk, order["id"])

        assert statement is not None
        assert (statement.earned, statement.earned_pending) == (Decimal(0), False)
        assert statement.available == Decimal("5.00")

    def test_switching_back_on_ends_the_closing(self, programme, client_user):
        self.switch(False)
        self.switch(True)

        assert LoyaltySettings.objects.get(pk=1).points_disabled_at is None
        assert balance(client_user)["closes_at"] is None


class TestValidity:
    def test_the_balance_expires_after_a_year_without_purchase(self, programme, client_user):
        old = credit(client_user, "12.00", available_in=-400)
        PointsEntry.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )

        expired = container.resolve(PointsFacade).expire()

        assert expired == 1
        assert PointsEntry.objects.get(kind="expiry").amount == Decimal("-12.00")
        assert balance(client_user)["available"] == "0.00"

    def test_points_given_back_on_a_cancelled_order_restart_the_count(
        self, programme, client_user, product
    ):
        old = credit(client_user, "12.00", available_in=-400)
        order = place(client_user, product, points="12")
        long_ago = timezone.now() - timedelta(days=400)
        PointsEntry.objects.filter(pk=old.pk).update(created_at=long_ago)
        Order.objects.filter(pk=order["id"]).update(created_at=long_ago, status="cancelled")

        status_changed(order["id"], OrderStatus.CANCELLED)

        assert container.resolve(PointsFacade).expire() == 0
        assert balance(client_user)["available"] == "12.00"

    def test_a_purchase_restarts_the_count_for_the_whole_balance(
        self, programme, client_user, product
    ):
        old = credit(client_user, "12.00", available_in=-400)
        PointsEntry.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=400)
        )
        place(client_user, product)

        assert container.resolve(PointsFacade).expire() == 0
        mine = balance(client_user)
        assert mine["available"] == "12.00"
        valid_until = datetime.fromisoformat(mine["next_expiry"])
        assert timedelta(days=360) < valid_until - timezone.now() <= timedelta(days=366)


class TestStatement:
    def test_the_invoice_prints_the_points_statement(self, programme, client_user, product):
        credit(client_user, "10.00")
        order = place(client_user, product, points="10")
        facade = container.resolve(PointsFacade)

        before = facade.invoice_statement(client_user.pk, order["id"])
        status_changed(order["id"], OrderStatus.DELIVERED)
        Order.objects.filter(pk=order["id"]).update(status="delivered")
        after = facade.invoice_statement(client_user.pk, order["id"])

        assert before is not None
        assert after is not None
        # before delivery: what the order will earn, pending
        assert (before.earned, before.earned_pending, before.used) == (
            Decimal("0.90"),
            True,
            Decimal("10.00"),
        )
        assert (after.earned, after.earned_pending) == (Decimal("0.90"), True)
        assert (after.available, after.orders_count) == (Decimal("0.00"), 1)

    def test_no_statement_while_the_programme_is_off(self, client_user, product):
        order = place(client_user, product)

        assert (
            container.resolve(PointsFacade).invoice_statement(client_user.pk, order["id"]) is None
        )


class TestConsistency:
    def test_failing_points_keep_the_order_unchanged(
        self, programme, client_user, product, monkeypatch
    ):
        order = place(client_user, product)
        monkeypatch.setattr(PointsFacade, "undone", Mock(side_effect=RuntimeError("boom")))

        with pytest.raises(RuntimeError):
            as_api(ManagerFactory.create()).post(
                f"/api/v1/bo/orders/{order['id']}/transition/", {"to": "cancelled"}
            )

        assert Order.objects.get(pk=order["id"]).status == "pending"


class TestLineReturns:
    @pytest.fixture
    def delivered(self, programme, client_user):
        product = ProductFactory.create(price=Decimal("100.00"), stock=20)
        credit(client_user, "80.00")
        response = as_api(client_user).post(
            "/api/v1/orders/",
            {
                "lines": lines(product, quantity=2),
                "payment_method": "cash",
                "address": ADDRESS,
                "points": "80",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="points-lines-0001",
        )
        order = Order.objects.get(pk=response.json()["id"])
        staff = as_api(ManagerFactory.create())
        reseller = ResellerFactory.create()
        staff.post(f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk})
        staff.post(
            f"/api/v1/bo/orders/{order.pk}/transition/",
            {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
        )
        order.refresh_from_db()
        return order, staff

    def give_back(self, staff, order, key):
        item = order.items.get()
        return staff.post(
            f"/api/v1/bo/orders/{order.pk}/items/{item.pk}/return/",
            {"quantity": 1},
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def entries(self, order, kind):
        return [entry.amount for entry in PointsEntry.objects.filter(order=order, kind=kind)]

    def test_each_unit_takes_back_its_share_of_the_earning_and_the_spending(
        self, client_user, delivered
    ):
        order, staff = delivered
        # 1 % of the 120 $ really paid (200 $ minus 80 points)
        assert (order.points, self.entries(order, "earn")) == (
            Decimal("80.00"),
            [Decimal("1.20")],
        )

        self.give_back(staff, order, "points-line-000001")

        assert self.entries(order, "reversal") == [Decimal("-0.60")]
        assert self.entries(order, "refund") == [Decimal("40.00")]
        detail = as_api(client_user).get(f"/api/v1/me/orders/{order.number}/").json()
        assert detail["points_earned"] == "0.60"

    def test_the_last_unit_closes_the_books_once(self, client_user, delivered):
        order, staff = delivered
        self.give_back(staff, order, "points-line-000002")

        self.give_back(staff, order, "points-line-000003")

        order.refresh_from_db()
        assert order.status == "returned"
        assert sum(self.entries(order, "reversal")) == Decimal("-1.20")
        assert sum(self.entries(order, "refund")) == Decimal("80.00")
        detail = as_api(client_user).get(f"/api/v1/me/orders/{order.number}/").json()
        assert detail["points_earned"] is None

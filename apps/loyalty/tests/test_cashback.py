from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.loyalty.handlers import settle_cashback
from apps.loyalty.models import CashbackEntry, LoyaltySettings, Membership
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from apps.orders.models import Order

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
    LoyaltySettings.objects.update_or_create(
        pk=1, defaults={"cashback_enabled": True, "membership_enabled": True}
    )


@pytest.fixture
def member():
    user = UserFactory.create()
    Membership.objects.create(
        user=user, plan="monthly", ends_at=timezone.now() + timedelta(days=30)
    )
    return user


@pytest.fixture
def product():
    return ProductFactory.create(price=Decimal("100.00"), stock=20)


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def credit(user, amount, *, available_in=-1, expires_in=300):
    now = timezone.now()
    return CashbackEntry.objects.create(
        user=user,
        kind="earn",
        amount=Decimal(amount),
        remaining=Decimal(amount),
        available_at=now + timedelta(days=available_in),
        expires_at=now + timedelta(days=expires_in),
    )


def lines(product, quantity=1):
    return [{"product_id": product.pk, "quantity": quantity}]


def place(user, product, *, use_cashback=False, key="checkout-0001"):
    response = as_api(user).post(
        "/api/v1/orders/",
        {
            "lines": lines(product),
            "payment_method": "cash",
            "address": ADDRESS,
            "use_cashback": use_cashback,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 201, response.json()
    return response.json()


def status_changed(order_id, status):
    order = Order.objects.get(pk=order_id)
    settle_cashback(
        OrderStatusChanged(
            order_id=order.pk,
            client_id=order.client_id,
            reseller_id=None,
            previous_status=OrderStatus.SHIPPING,
            status=status,
        )
    )


def balance(user):
    return as_api(user).get("/api/v1/me/cashback/").json()


class TestEarning:
    def test_delivery_earns_three_percent_after_the_return_period(self, programme, member, product):
        order = place(member, product)

        status_changed(order["id"], OrderStatus.DELIVERED)

        entry = CashbackEntry.objects.get(kind="earn")
        assert entry.amount == Decimal("3.00")
        assert timedelta(days=6) < entry.available_at - timezone.now() <= timedelta(days=7)
        assert balance(member) | {"next_expiry": None} == {
            "eligible": True,
            "available": "0.00",
            "pending": "3.00",
            "next_expiry": None,
        }
        detail = as_api(member).get(f"/api/v1/me/orders/{order['number']}/").json()
        assert detail["cashback_earned"] == "3.00"

    def test_delivering_twice_earns_once(self, programme, member, product):
        order = place(member, product)

        status_changed(order["id"], OrderStatus.DELIVERED)
        status_changed(order["id"], OrderStatus.DELIVERED)

        assert CashbackEntry.objects.filter(kind="earn").count() == 1

    def test_members_only_by_default(self, programme, product):
        client = UserFactory.create()
        order = place(client, product)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert not CashbackEntry.objects.exists()
        assert balance(client)["eligible"] is False

    def test_open_to_everyone_when_the_admin_says_so(self, programme, product):
        LoyaltySettings.objects.filter(pk=1).update(cashback_members_only=False)
        client = UserFactory.create()
        order = place(client, product)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert CashbackEntry.objects.get().amount == Decimal("3.00")

    def test_a_returned_order_loses_its_cashback(self, programme, member, product):
        order = place(member, product)
        status_changed(order["id"], OrderStatus.DELIVERED)

        status_changed(order["id"], OrderStatus.RETURNED)

        assert balance(member)["pending"] == "0.00"
        detail = as_api(member).get(f"/api/v1/me/orders/{order['number']}/").json()
        assert detail["cashback_earned"] is None


class TestSpending:
    def quote(self, user, product, use_cashback):
        return (
            as_api(user)
            .post(
                "/api/v1/checkout/quote/",
                {"lines": lines(product), "city": "Bukavu", "use_cashback": use_cashback},
                format="json",
            )
            .json()
        )

    def test_pays_up_to_half_of_the_products(self, programme, member, product):
        credit(member, "80.00")

        offered = self.quote(member, product, use_cashback=False)
        used = self.quote(member, product, use_cashback=True)

        assert (offered["cashback_available"], offered["cashback"]) == ("50.00", "0.00")
        assert (used["cashback"], used["total"]) == ("50.00", "50.00")

    def test_needs_the_minimum_balance(self, programme, member, product):
        credit(member, "0.50")

        assert self.quote(member, product, use_cashback=True)["cashback"] == "0.00"

    def test_pending_cashback_cannot_be_spent(self, programme, member, product):
        credit(member, "20.00", available_in=3)

        assert self.quote(member, product, use_cashback=True)["cashback"] == "0.00"

    def test_ordering_spends_the_oldest_credit_first(self, programme, member, product):
        later = credit(member, "40.00", expires_in=200)
        sooner = credit(member, "30.00", expires_in=20)

        order = place(member, product, use_cashback=True)

        saved = Order.objects.get(pk=order["id"])
        assert (saved.cashback, saved.total) == (Decimal("50.00"), Decimal("50.00"))
        later.refresh_from_db()
        sooner.refresh_from_db()
        assert (sooner.remaining, later.remaining) == (Decimal("0.00"), Decimal("20.00"))
        assert balance(member)["available"] == "20.00"

    def test_cancelling_gives_the_cashback_back(self, programme, member, product):
        credit(member, "60.00")
        order = place(member, product, use_cashback=True)

        status_changed(order["id"], OrderStatus.CANCELLED)

        assert balance(member)["available"] == "60.00"

    def test_spent_cashback_earns_nothing(self, programme, member, product):
        credit(member, "60.00")
        order = place(member, product, use_cashback=True)

        status_changed(order["id"], OrderStatus.DELIVERED)

        assert CashbackEntry.objects.get(order_id=order["id"], kind="earn").amount == Decimal(
            "1.50"
        )

    def test_nothing_when_the_programme_is_off(self, member, product):
        credit(member, "60.00")

        assert self.quote(member, product, use_cashback=True)["cashback"] == "0.00"


def test_unused_cashback_expires(programme, member):
    from apps.loyalty.facades import CashbackFacade
    from core.container import container

    credit(member, "12.00", expires_in=-1)

    assert container.resolve(CashbackFacade).expire() == 1
    assert CashbackEntry.objects.get(kind="expiry").amount == Decimal("-12.00")
    assert balance(member)["available"] == "0.00"

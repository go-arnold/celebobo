"""Store credit (avoir): issued for a change of mind, spent on products and delivery, 6 months."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ManagerFactory, ResellerFactory, UserFactory
from apps.catalog.tests.factories import ProductFactory
from apps.credit.domain.rules import expiry_of
from apps.credit.facades import StoreCreditFacade
from apps.credit.models import CreditEntry
from apps.credit.services.credit import StoreCreditService
from apps.orders.models import Order, OrderItem
from apps.orders.selectors import convertible_order
from core.container import container
from core.domain.actor import Actor

pytestmark = pytest.mark.django_db

ADDRESS = {
    "recipient": "Aline Mbuyi",
    "phone": "+243 81 234 5678",
    "line1": "Av. Lumumba n°12",
    "quarter": "Ibanda",
    "city": "Bukavu",
    "country": "RD Congo",
}
BO = "/api/v1/bo/orders/"


def as_api(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def service() -> StoreCreditService:
    return StoreCreditService(clock=timezone.now)


def give(user, amount: str, *, days_ago: int = 0) -> CreditEntry:
    entry = service().issue(user.pk, Decimal(amount), note="Test")
    assert entry is not None
    if days_ago:
        issued = timezone.now() - timedelta(days=days_ago)
        CreditEntry.objects.filter(pk=entry.pk).update(
            created_at=issued, expires_at=expiry_of(issued)
        )
        entry.refresh_from_db()
    return entry


@pytest.fixture
def client_user():
    return UserFactory.create()


@pytest.fixture
def product():
    return ProductFactory.create(price=Decimal("100.00"), stock=20)


def body(product, **extra):
    return {
        "lines": [{"product_id": product.pk, "quantity": 1}],
        "payment_method": "cash",
        "address": ADDRESS,
        **extra,
    }


def place(user, product, credit: str, *, key="checkout-0001", expect=201):
    response = as_api(user).post(
        "/api/v1/orders/",
        body(product, store_credit=credit),
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == expect, response.json()
    return response.json()


def available(user) -> Decimal:
    return service().available(user.pk)


class TestLedger:
    def test_six_months_and_the_closest_expiry_first(self, client_user):
        old = give(client_user, "20.00", days_ago=100)
        new = give(client_user, "30.00")

        service().spend(client_user.pk, order_id=None, amount=Decimal("25.00"))  # type: ignore[arg-type]

        old.refresh_from_db()
        new.refresh_from_db()
        assert (old.remaining, new.remaining) == (Decimal("0.00"), Decimal("25.00"))
        assert new.expires_at is not None
        assert new.expires_at.date() == expiry_of(new.created_at).date()

    def test_unused_credit_expires(self, client_user):
        give(client_user, "20.00", days_ago=200)

        assert service().expire() == 1

        assert available(client_user) == 0
        assert CreditEntry.objects.filter(kind="expired", amount=Decimal("-20.00")).exists()

    def test_the_balance_page(self, client_user):
        give(client_user, "40.00")

        page = as_api(client_user).get("/api/v1/me/store-credit/").json()

        assert page["available"] == "40.00"
        assert page["next_expiry"] is not None
        assert page["history"][0]["kind_label"] == "Avoir reçu"


class TestCheckout:
    def test_the_quote_offers_it_delivery_included(self, client_user, product):
        give(client_user, "150.00")

        quote = (
            as_api(client_user)
            .post(
                "/api/v1/checkout/quote/",
                {"lines": body(product)["lines"], "city": "Bukavu", "store_credit": "150"},
                format="json",
            )
            .json()
        )

        # products and delivery: the credit pays all of it
        due = Decimal(quote["subtotal"]) + Decimal(quote["shipping_fee"])
        assert Decimal(quote["store_credit"]) == due
        assert Decimal(quote["store_credit_available"]) == due
        assert quote["total"] == "0.00"

    def test_spent_on_products_first_then_delivery(self, client_user, product):
        give(client_user, "150.00")

        order = place(client_user, product, "150")

        saved = Order.objects.get(pk=order["id"])
        item = OrderItem.objects.get(order=saved)
        due = saved.subtotal + saved.shipping_fee
        assert (saved.store_credit, saved.total) == (due, Decimal("0.00"))
        assert (item.credit, item.amount_paid) == (Decimal("100.00"), Decimal("0.00"))
        assert available(client_user) == Decimal("150.00") - due
        assert Decimal(order["store_credit"]) == due

    def test_more_than_the_balance_is_refused(self, client_user, product):
        give(client_user, "10.00")

        response = place(client_user, product, "50", expect=409)

        assert response["code"] == "store_credit_unavailable"

    def test_an_order_paid_with_credit_earns_no_commission(self, client_user, product):
        give(client_user, "30.00")
        order = place(client_user, product, "30")

        convertible = convertible_order(Actor.system(), order["id"])

        assert convertible.store_credit == Decimal("30.00")
        assert convertible.real_money_only is False


class TestGivenBack:
    def test_a_cancelled_order_gives_it_back(
        self, client_user, product, django_capture_on_commit_callbacks
    ):
        give(client_user, "50.00")
        order = place(client_user, product, "50")

        with django_capture_on_commit_callbacks(execute=True):
            as_api(ManagerFactory.create()).post(
                f"{BO}{order['id']}/transition/", {"to": "cancelled"}
            )

        assert available(client_user) == Decimal("50.00")
        assert CreditEntry.objects.filter(kind="restored").count() == 1

    def test_a_returned_line_gives_back_its_share(
        self, client_user, product, django_capture_on_commit_callbacks
    ):
        give(client_user, "40.00")
        order = place(client_user, product, "40")
        staff = as_api(ManagerFactory.create())
        staff.post(f"{BO}{order['id']}/assign/", {"reseller_id": ResellerFactory.create().pk})
        staff.post(
            f"{BO}{order['id']}/transition/",
            {"to": "delivered", "reason": "Remise vérifiée par téléphone"},
        )
        item = OrderItem.objects.get(order_id=order["id"])

        with django_capture_on_commit_callbacks(execute=True):
            staff.post(
                f"{BO}{order['id']}/items/{item.pk}/return/",
                {"quantity": 1, "reason": "Retour"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="line-return-0001",
            )

        assert available(client_user) == Decimal("40.00")

    def test_a_lower_price_gives_back_the_excess(self, client_user, product):
        give(client_user, "150.00")
        order = place(client_user, product, "150")
        spent = Order.objects.get(pk=order["id"]).store_credit

        container.resolve(StoreCreditFacade).repriced(order["id"], Decimal("60.00"))

        # the order now needs 60 $ of credit: the rest goes back
        assert available(client_user) == Decimal("150.00") - spent + (spent - Decimal("60.00"))

    def test_a_change_of_mind_becomes_credit(self, client_user):
        container.resolve(StoreCreditFacade).line_returned(
            client_user.pk, None, credit=Decimal(0), paid=Decimal("80.00"), as_credit=True
        )

        entry = CreditEntry.objects.get(kind="issued")
        assert entry.amount == Decimal("80.00")
        assert entry.expires_at is not None
        assert entry.expires_at.date() == expiry_of(entry.created_at).date()

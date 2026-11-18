from decimal import Decimal

import pytest

from apps.accounts.tests.factories import ResellerFactory
from apps.messaging.models import Notification, PriceProposal
from apps.messaging.tests.conftest import thread_of
from apps.orders.models import Order, ShippingZone
from apps.orders.tests.conftest import ADDRESS

pytestmark = pytest.mark.django_db(transaction=True)

FAR = {**ADDRESS, "city": "Kisangani"}


@pytest.fixture
def quoted_order(as_user, manager, reseller, client_user, product) -> Order:
    # transactional tests flush the migrated zones: the default zone is quoted on request
    ShippingZone.objects.filter(is_default=True).update(is_default=False)
    ShippingZone.objects.create(
        name="Reste du pays", fee=Decimal(0), pricing="quote", is_default=True
    )
    placed = as_user(client_user).post(
        "/api/v1/orders/",
        {
            "lines": [{"product_id": product.pk, "quantity": 1}],
            "payment_method": "cash",
            "address": FAR,
        },
        HTTP_IDEMPOTENCY_KEY="shipping-quote-0001",
    )
    assert placed.status_code == 201, placed.json()
    order = Order.objects.get(number=placed.json()["number"])
    assigned = as_user(manager).post(
        f"/api/v1/bo/orders/{order.pk}/assign/", {"reseller_id": reseller.pk}
    )
    assert assigned.status_code == 200, assigned.json()
    order.refresh_from_db()
    return order


def quote(api, order, fee, estimate="3 à 5 jours", reason="Transport par bus"):
    return api.post(
        f"/api/v1/conversations/{thread_of(order).pk}/shipping-quotes/",
        {"fee": fee, "delivery_estimate": estimate, "reason": reason},
    )


def respond(api, message, accept):
    return api.post(
        f"/api/v1/price-proposals/{message.json()['metadata']['proposal_id']}/respond/",
        {"accept": accept},
    )


class TestShippingQuotes:
    def test_the_order_waits_for_a_fee(self, as_user, client_user, reseller, quoted_order):
        detail = as_user(client_user).get(f"/api/v1/me/orders/{quoted_order.number}/").json()
        staff = as_user(reseller).get(f"/api/v1/bo/orders/{quoted_order.pk}/").json()

        assert (quoted_order.shipping_fee, quoted_order.total) == (Decimal(0), Decimal("120.00"))
        assert detail["awaiting_shipping_quote"] is True
        assert detail["shipping_zone"] == "Reste du pays"
        # nothing is fixed yet: the reseller cannot confirm and the client may still cancel
        assert staff["allowed_transitions"] == []
        assert detail["allowed_transitions"] == ["cancelled"]

    def test_reseller_quotes_and_client_accepts(self, as_user, client_user, reseller, quoted_order):
        quoted = quote(as_user(reseller), quoted_order, "12.50")
        accepted = respond(as_user(client_user), quoted, accept=True)

        assert quoted.status_code == 201, quoted.json()
        assert quoted.json()["kind"] == "shipping_quote"
        assert quoted.json()["metadata"]["proposed_fee"] == "12.50"
        assert quoted.json()["metadata"]["order_number"] == quoted_order.number
        assert accepted.json()["metadata"]["status"] == "accepted"
        order = Order.objects.get(pk=quoted_order.pk)
        assert (order.shipping_fee, order.total) == (Decimal("12.50"), Decimal("132.50"))
        assert order.delivery_estimate == "3 à 5 jours"
        assert order.awaiting_shipping_quote is False
        assert thread_of(order).messages.order_by("-pk").first().body == (
            "Frais de livraison acceptés : 12.50 $ (3 à 5 jours)."
        )
        staff = as_user(reseller).get(f"/api/v1/bo/orders/{order.pk}/").json()
        assert staff["allowed_transitions"] == ["confirmed"]
        assert Notification.objects.get(recipient=client_user, kind="shipping_quoted").body == (
            f"Commande {order.number} : livraison à 12.50 $ (3 à 5 jours). "
            "Acceptez-la ou annulez sans frais."
        )
        assert Notification.objects.get(recipient=reseller, kind="shipping_answered").body == (
            f"Le client a accepté les frais de 12.50 $ pour la commande {order.number}."
        )

    def test_an_accepted_fee_can_no_longer_change(
        self, as_user, client_user, reseller, quoted_order
    ):
        respond(as_user(client_user), quote(as_user(reseller), quoted_order, "10.00"), True)

        again = quote(as_user(reseller), quoted_order, "8.00")

        assert again.json()["code"] == "shipping_not_quotable"
        assert Order.objects.get(pk=quoted_order.pk).shipping_fee == Decimal("10.00")

    def test_refusal_keeps_the_order_open_for_a_new_quote(
        self, as_user, client_user, reseller, quoted_order
    ):
        refused = respond(as_user(client_user), quote(as_user(reseller), quoted_order, "20"), False)
        second = quote(as_user(reseller), quoted_order, "15.00")

        assert refused.json()["metadata"]["status"] == "refused"
        assert second.status_code == 201
        order = Order.objects.get(pk=quoted_order.pk)
        assert (order.shipping_fee, order.awaiting_shipping_quote) == (Decimal(0), True)

    def test_a_new_quote_supersedes_the_pending_one(self, as_user, reseller, quoted_order):
        first = quote(as_user(reseller), quoted_order, "20.00")
        quote(as_user(reseller), quoted_order, "18.00")

        assert list(PriceProposal.objects.order_by("pk").values_list("status", flat=True)) == [
            "superseded",
            "pending",
        ]
        message = thread_of(quoted_order).messages.get(pk=first.json()["id"])
        assert message.metadata["status"] == "superseded"

    def test_the_client_cancels_free_of_charge_instead(
        self, as_user, client_user, reseller, quoted_order
    ):
        quote(as_user(reseller), quoted_order, "25.00")

        cancelled = as_user(client_user).post(
            f"/api/v1/me/orders/{quoted_order.number}/cancel/", {"reason": "changed_mind"}
        )

        assert cancelled.status_code == 200, cancelled.json()
        assert Order.objects.get(pk=quoted_order.pk).status == "cancelled"

    def test_only_the_assigned_reseller_or_staff_quote(
        self, as_user, client_user, manager, quoted_order
    ):
        assert quote(as_user(client_user), quoted_order, "5.00").status_code == 403
        assert quote(as_user(ResellerFactory.create()), quoted_order, "5.00").status_code == 404
        assert quote(as_user(manager), quoted_order, "5.00").status_code == 201

    def test_fixed_fee_orders_are_not_quoted(self, as_user, reseller, assigned_order):
        response = quote(as_user(reseller), assigned_order, "5.00")

        assert response.json()["code"] == "shipping_not_quotable"

    def test_the_fee_cannot_be_negative(self, as_user, reseller, quoted_order):
        assert quote(as_user(reseller), quoted_order, "-1.00").status_code == 400

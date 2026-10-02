from decimal import Decimal

import pytest
from django.core import mail

from apps.accounts.models import NotificationPreference
from apps.accounts.tests.factories import ResellerFactory
from apps.messaging.domain.enums import NotificationKind
from apps.messaging.domain.notifications import preview, render
from apps.messaging.models import Conversation, Notification, PriceProposal
from apps.messaging.tests.conftest import thread_of
from apps.orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)


def propose(api, conversation, item_id, price, reason="Remise fidélité"):
    return api.post(
        f"/api/v1/conversations/{conversation.pk}/price-proposals/",
        {"item_id": item_id, "new_price": price, "reason": reason},
    )


class TestPriceProposals:
    def test_reseller_proposes_and_client_accepts(
        self, as_user, client_user, reseller, assigned_order
    ):
        conversation = thread_of(assigned_order)
        item = assigned_order.items.get()

        proposed = propose(as_user(reseller), conversation, item.pk, "99.00")
        proposal_id = proposed.json()["metadata"]["proposal_id"]
        accepted = as_user(client_user).post(
            f"/api/v1/price-proposals/{proposal_id}/respond/", {"accept": True}
        )

        assert proposed.status_code == 201
        assert proposed.json()["kind"] == "price_proposal"
        assert proposed.json()["metadata"]["previous_price"] == "120.00"
        assert accepted.json()["metadata"]["status"] == "accepted"
        order = Order.objects.get(pk=assigned_order.pk)
        assert order.items.get().unit_price == Decimal("99.00")
        assert order.subtotal == Decimal("99.00")
        assert order.total == order.subtotal + order.shipping_fee
        assert conversation.messages.order_by("-pk").first().body == (
            "Proposition acceptée : 120.00 $ → 99.00 $."
        )
        assert Notification.objects.filter(recipient=client_user, kind="price_proposed").exists()
        answered = Notification.objects.get(recipient=reseller, kind="price_answered")
        assert answered.body == "Le client a accepté le prix de 99.00 $ pour Galaxy A55."

    def test_refusal_keeps_the_price(self, as_user, client_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)
        item = assigned_order.items.get()
        proposal_id = propose(as_user(reseller), conversation, item.pk, "90.00").json()["metadata"][
            "proposal_id"
        ]

        response = as_user(client_user).post(
            f"/api/v1/price-proposals/{proposal_id}/respond/", {"accept": False}
        )
        again = as_user(client_user).post(
            f"/api/v1/price-proposals/{proposal_id}/respond/", {"accept": True}
        )

        assert response.json()["metadata"]["status"] == "refused"
        assert again.status_code == 409
        assert Order.objects.get(pk=assigned_order.pk).items.get().unit_price == Decimal("120.00")

    def test_a_new_proposal_supersedes_the_pending_one(self, as_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)
        item = assigned_order.items.get()

        propose(as_user(reseller), conversation, item.pk, "110.00")
        propose(as_user(reseller), conversation, item.pk, "105.00")

        assert list(PriceProposal.objects.order_by("pk").values_list("status", flat=True)) == [
            "superseded",
            "pending",
        ]

    def test_price_cannot_exceed_the_catalogue_price(self, as_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)

        response = propose(as_user(reseller), conversation, assigned_order.items.get().pk, "150.00")

        assert response.json()["code"] == "invalid_proposed_price"

    def test_paid_orders_are_frozen(self, as_user, manager, reseller, assigned_order):
        as_user(manager).post(f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": "paid"})
        conversation = thread_of(assigned_order)

        response = propose(as_user(reseller), conversation, assigned_order.items.get().pk, "100.00")

        assert response.json()["code"] == "item_not_adjustable"

    def test_only_the_client_answers_and_only_staff_or_assignee_propose(
        self, as_user, client_user, reseller, assigned_order
    ):
        conversation = thread_of(assigned_order)
        item_id = assigned_order.items.get().pk

        assert propose(as_user(client_user), conversation, item_id, "100.00").status_code == 403
        assert (
            propose(as_user(ResellerFactory.create()), conversation, item_id, "100.00").status_code
            == 404
        )
        proposal_id = propose(as_user(reseller), conversation, item_id, "100.00").json()[
            "metadata"
        ]["proposal_id"]
        assert (
            as_user(reseller)
            .post(f"/api/v1/price-proposals/{proposal_id}/respond/", {"accept": True})
            .status_code
            == 403
        )


class TestSupport:
    def test_client_opens_staff_assigns_reseller_answers(
        self, as_user, client_user, manager, reseller
    ):
        opened = as_user(client_user).post(
            "/api/v1/conversations/", {"message": "Avez-vous le Pixel 9 en stock ?"}
        )
        conversation_id = opened.json()["id"]
        staff_alert = Notification.objects.get(recipient=manager, kind="support_request")

        assigned = as_user(manager).post(
            f"/api/v1/conversations/{conversation_id}/assign/", {"reseller_id": reseller.pk}
        )
        as_user(reseller).post(
            f"/api/v1/conversations/{conversation_id}/messages/", {"body": "Oui, dès demain."}
        )

        assert opened.status_code == 201
        assert opened.json()["kind"] == "support"
        assert opened.json()["subject"] == "Avez-vous le Pixel 9 en stock ?"
        assert (
            staff_alert.body
            == "Aline Mbuyi a ouvert une discussion : Avez-vous le Pixel 9 en stock ?"
        )
        assert assigned.json()["reseller"]["id"] == reseller.pk
        assert Notification.objects.filter(
            recipient=reseller, kind="conversation_assigned"
        ).exists()
        assert Notification.objects.filter(recipient=client_user, kind="new_message").exists()

    def test_order_threads_cannot_be_assigned_manually(
        self, as_user, manager, reseller, assigned_order
    ):
        conversation = thread_of(assigned_order)

        response = as_user(manager).post(
            f"/api/v1/conversations/{conversation.pk}/assign/", {"reseller_id": reseller.pk}
        )

        assert response.json()["code"] == "not_a_support_conversation"

    def test_resellers_cannot_assign(self, as_user, client_user, reseller):
        conversation_id = (
            as_user(client_user).post("/api/v1/conversations/", {"message": "Bonjour"}).json()["id"]
        )

        response = as_user(reseller).post(
            f"/api/v1/conversations/{conversation_id}/assign/", {"reseller_id": reseller.pk}
        )

        assert response.status_code == 403


class TestNotificationsApi:
    def test_inbox_read_and_read_all(self, as_user, client_user, assigned_order):
        api = as_user(client_user)

        inbox = api.get("/api/v1/notifications/").json()
        first_id = inbox["results"][0]["id"]
        api.post(f"/api/v1/notifications/{first_id}/read/")
        after_one = api.get("/api/v1/notifications/", {"unread": "true"}).json()
        cleared = api.post("/api/v1/notifications/read-all/").json()

        assert inbox["meta"]["unread"] >= 1
        assert first_id not in [item["id"] for item in after_one["results"]]
        assert cleared["updated"] == after_one["meta"]["count"]
        assert api.get("/api/v1/notifications/unread-counts/").json()["notifications"] == 0

    def test_foreign_notifications_cannot_be_read(
        self, as_user, client_user, manager, assigned_order
    ):
        foreign = Notification.objects.filter(recipient=manager).earliest("pk")

        response = as_user(client_user).post(f"/api/v1/notifications/{foreign.pk}/read/")

        assert response.status_code == 404

    def test_email_respects_preferences(self, as_user, manager, client_user, place_order):
        NotificationPreference.objects.create(
            user=manager, preferences={"order_assigned": {"email": False, "push": True}}
        )

        place_order(client_user)

        assert Notification.objects.filter(recipient=manager, kind="order_placed").exists()
        assert manager.email not in [address for message in mail.outbox for address in message.to]


class TestTemplates:
    def test_render_and_preview(self):
        rendered = render(NotificationKind.ORDER_STATUS, number="CB-AAAA-BBBB", status="Payée")

        assert rendered.title == "Commande CB-AAAA-BBBB : Payée"
        assert rendered.link == "/compte/commandes/CB-AAAA-BBBB"
        assert rendered.topic == "status_changed"
        assert preview("x" * 200, limit=10) == "xxxxxxxxx…"
        assert not Conversation.objects.exists()

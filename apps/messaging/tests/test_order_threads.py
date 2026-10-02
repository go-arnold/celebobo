import pytest
from django.core import mail

from apps.accounts.tests.factories import ResellerFactory, UserFactory
from apps.messaging.models import Conversation, Message, Notification
from apps.messaging.tests.conftest import thread_of

pytestmark = pytest.mark.django_db(transaction=True)


def messages_of(conversation: Conversation) -> list[tuple[str, str]]:
    return list(conversation.messages.order_by("pk").values_list("kind", "body"))


class TestOrderThread:
    def test_placing_an_order_opens_its_thread(self, as_user, client_user, place_order):
        order = place_order(client_user)

        conversation = thread_of(order)
        assert conversation.kind == "order"
        assert conversation.subject == f"Commande {order.number}"
        assert messages_of(conversation) == [
            ("system", f"Discussion exclusivement consacrée à la commande {order.number}.")
        ]
        detail = as_user(client_user).get(f"/api/v1/me/orders/{order.number}/").json()
        assert detail["conversation_id"] == conversation.pk

    def test_staff_are_notified_of_new_orders(self, manager, client_user, place_order):
        order = place_order(client_user)

        notification = Notification.objects.get(recipient=manager)
        assert notification.kind == "order_placed"
        assert notification.title == f"Nouvelle commande {order.number}"
        assert notification.link == f"/admin/commandes/{order.pk}"
        assert [message.to for message in mail.outbox] == [[manager.email]]

    def test_assignment_brings_the_reseller_in(self, as_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)

        assert conversation.assigned_reseller == reseller
        assert messages_of(conversation)[-1] == (
            "system",
            "Patrick Kabasele a rejoint la discussion.",
        )
        assert Notification.objects.filter(recipient=reseller, kind="order_assigned").exists()
        assert as_user(reseller).get(f"/api/v1/conversations/{conversation.pk}/").status_code == 200

    def test_declining_removes_the_reseller(self, as_user, reseller, assigned_order):
        as_user(reseller).post(
            f"/api/v1/bo/orders/{assigned_order.pk}/decline/", {"reason": "Absent"}
        )

        conversation = thread_of(assigned_order)
        assert conversation.assigned_reseller is None
        assert as_user(reseller).get(f"/api/v1/conversations/{conversation.pk}/").status_code == 404

    def test_client_is_notified_of_status_changes(
        self, as_user, client_user, reseller, assigned_order
    ):
        as_user(reseller).post(
            f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": "confirmed"}
        )

        titles = list(
            Notification.objects.filter(recipient=client_user, kind="order_status")
            .order_by("pk")
            .values_list("title", flat=True)
        )
        assert titles == [
            f"Commande {assigned_order.number} : Assignée",
            f"Commande {assigned_order.number} : Confirmée",
        ]
        assert not Notification.objects.filter(recipient=reseller, kind="order_status").exists()

    def test_finished_orders_close_their_thread(self, as_user, manager, assigned_order):
        as_user(manager).post(
            f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": "delivered"}
        )

        conversation = thread_of(assigned_order)
        assert conversation.status == "closed"
        assert messages_of(conversation)[-1] == ("system", "Commande livrée : discussion clôturée.")


class TestMessaging:
    def test_participants_exchange_messages(self, as_user, client_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)
        url = f"/api/v1/conversations/{conversation.pk}/messages/"

        sent = as_user(client_user).post(
            url, {"body": "  Bonjour, livraison demain ?  ", "client_msg_id": "c-1"}
        )
        replay = as_user(client_user).post(
            url, {"body": "Bonjour, livraison demain ?", "client_msg_id": "c-1"}
        )
        as_user(reseller).post(url, {"body": "Oui, avant midi."})

        assert sent.status_code == 201
        assert sent.json()["body"] == "Bonjour, livraison demain ?"
        assert replay.json()["id"] == sent.json()["id"]
        history = as_user(client_user).get(url).json()["results"]
        assert [item["body"] for item in history[:2]] == [
            "Oui, avant midi.",
            "Bonjour, livraison demain ?",
        ]

    def test_new_message_alerts_are_deduplicated(
        self, as_user, client_user, reseller, assigned_order
    ):
        conversation = thread_of(assigned_order)
        url = f"/api/v1/conversations/{conversation.pk}/messages/"

        for body in ("Un", "Deux", "Trois"):
            as_user(reseller).post(url, {"body": body})

        alerts = Notification.objects.filter(recipient=client_user, kind="new_message")
        assert alerts.count() == 1
        assert alerts.get().body == "Patrick Kabasele : Un"

        as_user(client_user).post(f"/api/v1/conversations/{conversation.pk}/read/", {})
        assert not Notification.objects.filter(
            recipient=client_user, kind="new_message", is_read=False
        ).exists()

    def test_unread_counts_follow_reads(self, as_user, client_user, reseller, assigned_order):
        conversation = thread_of(assigned_order)
        as_user(reseller).post(
            f"/api/v1/conversations/{conversation.pk}/messages/", {"body": "Bonjour"}
        )
        client_api = as_user(client_user)

        listed = client_api.get("/api/v1/conversations/").json()["results"][0]
        before = client_api.get("/api/v1/notifications/unread-counts/").json()
        client_api.post(f"/api/v1/conversations/{conversation.pk}/read/", {})
        after = client_api.get("/api/v1/notifications/unread-counts/").json()

        assert listed["unread_count"] == 1
        assert listed["last_message"]["body"] == "Bonjour"
        assert before["conversations"] == 1
        assert after["conversations"] == 0

    def test_message_history_is_cursor_paginated(self, as_user, client_user, assigned_order):
        conversation = thread_of(assigned_order)
        url = f"/api/v1/conversations/{conversation.pk}/messages/"
        api = as_user(client_user)
        for index in range(5):
            api.post(url, {"body": f"Message {index}"})

        first = api.get(url, {"limit": 3}).json()
        second = api.get(url, {"limit": 3, "before": first["meta"]["next_before"]}).json()

        assert [item["body"] for item in first["results"]] == [
            "Message 4",
            "Message 3",
            "Message 2",
        ]
        assert second["results"][0]["body"] == "Message 1"

    def test_strangers_cannot_read_or_write(self, as_user, assigned_order):
        conversation = thread_of(assigned_order)

        for user in (UserFactory.create(), ResellerFactory.create()):
            api = as_user(user)
            assert api.get(f"/api/v1/conversations/{conversation.pk}/messages/").status_code == 404
            assert (
                api.post(
                    f"/api/v1/conversations/{conversation.pk}/messages/", {"body": "Hello"}
                ).status_code
                == 404
            )

    def test_empty_messages_are_rejected(self, as_user, client_user, assigned_order):
        conversation = thread_of(assigned_order)

        response = as_user(client_user).post(
            f"/api/v1/conversations/{conversation.pk}/messages/", {"body": "   "}
        )

        assert response.json()["code"] == "empty_message"

    def test_closed_threads_are_read_only_until_reopened(
        self, as_user, client_user, reseller, assigned_order
    ):
        conversation = thread_of(assigned_order)
        url = f"/api/v1/conversations/{conversation.pk}/"

        assert as_user(client_user).post(f"{url}close/").status_code == 403
        assert as_user(reseller).post(f"{url}close/").json()["status"] == "closed"
        blocked = as_user(client_user).post(f"{url}messages/", {"body": "Encore là ?"})
        assert blocked.json()["code"] == "conversation_closed"
        assert as_user(reseller).post(f"{url}reopen/").json()["status"] == "open"
        assert Message.objects.filter(
            conversation=conversation, body="Discussion rouverte."
        ).exists()

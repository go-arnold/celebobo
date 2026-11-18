import pytest
from django.core import mail

from apps.accounts.models import NotificationPreference
from apps.messaging.models import Notification
from apps.orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_client_gets_the_code_by_email_whatever_their_preferences(
    as_user, client_user, reseller, assigned_order
):
    NotificationPreference.objects.create(
        user=client_user, preferences={"status_changed": {"email": False, "push": False}}
    )

    as_user(reseller).post(
        f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": "confirmed"}
    )

    code = Order.objects.get(pk=assigned_order.pk).delivery_code
    note = Notification.objects.get(kind="delivery_code")
    assert note.recipient_id == client_user.pk
    assert code in note.body
    sent = [message for message in mail.outbox if client_user.email in message.to]
    assert any(code in message.body for message in sent)


def test_staff_are_alerted_when_the_code_locks(as_user, manager, reseller, assigned_order):
    api = as_user(reseller)
    for status in ("confirmed", "paid", "shipping"):
        api.post(f"/api/v1/bo/orders/{assigned_order.pk}/transition/", {"to": status})
    code = Order.objects.get(pk=assigned_order.pk).delivery_code
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"

    for _ in range(5):
        api.post(
            f"/api/v1/bo/orders/{assigned_order.pk}/transition/",
            {"to": "delivered", "delivery_code": wrong},
        )

    alert = Notification.objects.get(kind="delivery_code_locked", recipient=manager)
    assert alert.link == f"/admin/commandes/{assigned_order.pk}"
    assert not Notification.objects.filter(kind="delivery_code_locked", recipient=reseller).exists()

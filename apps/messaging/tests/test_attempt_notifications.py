from datetime import datetime

import pytest
from django.utils import timezone

from apps.messaging.models import Notification
from apps.orders.models import DeliveryAttempt, Order

pytestmark = pytest.mark.django_db(transaction=True)


def out_for_delivery(as_user, reseller, order) -> None:
    api = as_user(reseller)
    for status in ("confirmed", "paid", "shipping"):
        api.post(f"/api/v1/bo/orders/{order.pk}/transition/", {"to": status})


def test_the_client_hears_about_a_missed_delivery(as_user, client_user, reseller, assigned_order):
    out_for_delivery(as_user, reseller, assigned_order)

    as_user(reseller).post(
        f"/api/v1/bo/orders/{assigned_order.pk}/delivery-attempts/", {"reason": "unreachable"}
    )

    note = Notification.objects.get(kind="delivery_attempt")
    assert note.recipient_id == client_user.pk
    assert note.body.startswith("Le revendeur n'a pas pu vous livrer (client injoignable).")


def test_after_two_working_days_staff_refund_within_five_working_days(
    as_user, manager, reseller, assigned_order
):
    out_for_delivery(as_user, reseller, assigned_order)
    for day in (16, 17):
        DeliveryAttempt.objects.create(
            order=assigned_order,
            reason="client_absent",
            created_at=timezone.make_aware(datetime(2026, 11, day, 10)),
        )

    as_user(reseller).post(
        f"/api/v1/bo/orders/{assigned_order.pk}/delivery-attempts/", {"reason": "client_absent"}
    )

    order = Order.objects.get(pk=assigned_order.pk)
    due = Notification.objects.get(kind="refund_due", recipient=manager)
    assert due.body == (
        f"La commande {order.number}, déjà payée, a été annulée : {order.refund_due} $ à rendre "
        "au client sous 5 jours ouvrables, frais de livraison déduits."
    )
    # the cancellation has its own notification: no "missed delivery" for the last attempt
    assert not Notification.objects.filter(kind="delivery_attempt").exists()

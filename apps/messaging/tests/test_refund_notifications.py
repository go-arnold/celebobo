import pytest

from apps.messaging.models import Notification
from apps.orders.models import Order

pytestmark = pytest.mark.django_db(transaction=True)


def test_a_cancelled_paid_order_alerts_staff_then_the_client(
    as_user, client_user, reseller, manager, assigned_order
):
    Order.objects.filter(pk=assigned_order.pk).update(status="paid")

    as_user(client_user).post(
        f"/api/v1/me/orders/{assigned_order.number}/cancel/", {"reason": "changed_mind"}
    )
    as_user(manager).post(f"/api/v1/bo/orders/{assigned_order.pk}/refund/", {"note": "MP-1"})

    due = Notification.objects.filter(kind="refund_due")
    assert set(due.values_list("recipient_id", flat=True)) == {manager.pk, reseller.pk}
    assert due.first().body == (  # type: ignore[union-attr]
        f"La commande {assigned_order.number}, déjà payée, a été annulée : "
        f"{assigned_order.total} $ à rendre au client sous 72 h."
    )
    refunded = Notification.objects.get(kind="order_refunded")
    assert refunded.recipient_id == client_user.pk
    assert refunded.link == f"/compte/commandes/{assigned_order.number}"

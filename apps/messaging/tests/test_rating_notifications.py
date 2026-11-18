import pytest

from apps.messaging.models import Notification

pytestmark = pytest.mark.django_db(transaction=True)


def test_the_reseller_hears_about_a_new_rating(
    as_user, client_user, manager, reseller, assigned_order
):
    as_user(manager).post(
        f"/api/v1/bo/orders/{assigned_order.pk}/transition/",
        {"to": "delivered", "reason": "Remise vérifiée"},
    )

    as_user(client_user).post(
        f"/api/v1/me/orders/{assigned_order.number}/rating/", {"score": 5, "comment": "Parfait"}
    )

    note = Notification.objects.get(kind="reseller_rated")
    assert note.recipient_id == reseller.pk
    assert note.title == "Nouvelle note : 5/5"

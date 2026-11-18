import pytest
from django.core import mail

from apps.documents.models import DeliveryReceipt
from apps.orders.models import Order
from core.mail import build_message, serialize_message

BO = "/api/v1/bo/orders/"
MINE = "/api/v1/me/orders/"
VERIFY = "/api/v1/receipts/verify/"


@pytest.fixture
def order(as_user, shopper, phone, place_order, *, manager, reseller) -> Order:
    order = Order.objects.get(number=place_order(shopper, phone, quantity=2)["number"])
    as_user(manager).post(f"{BO}{order.pk}/assign/", {"reseller_id": reseller.pk})
    return order


def receipt_mails():
    return [message for message in mail.outbox if "reçu de livraison" in message.subject]


def deliver(as_user, reseller, order) -> None:
    api = as_user(reseller)
    for status in ("confirmed", "paid", "shipping"):
        api.post(f"{BO}{order.pk}/transition/", {"to": status})
    code = Order.objects.values_list("delivery_code", flat=True).get(pk=order.pk)
    response = api.post(f"{BO}{order.pk}/transition/", {"to": "delivered", "delivery_code": code})
    assert response.json()["status"] == "delivered"


@pytest.mark.django_db(transaction=True)
def test_delivery_issues_a_signed_receipt_and_emails_it(
    as_user, shopper, reseller, order, renderer
):
    deliver(as_user, reseller, order)

    receipt = DeliveryReceipt.objects.get(order_id=order.pk)
    assert receipt.number == f"R-{order.number}"
    assert receipt.payload["confirmation"] == "Remise confirmée avec le code de livraison du client"
    assert receipt.payload["confirmed_by"] == "Patrick Kabasele"
    assert receipt.payload["total"] == str(order.total)
    assert len(receipt.signature) == 64
    assert receipt.emailed_at is not None
    sent = receipt_mails()
    assert len(sent) == 1
    assert sent[0].to == [shopper.email]
    assert sent[0].attachments[0][0] == f"recu-livraison-{order.number}.pdf"
    template, context = renderer.calls[-1]
    assert template == "documents/delivery_receipt.html"
    assert context["verify_link"].endswith(
        f"/verifier-recu?numero={receipt.number}&signature={receipt.signature}"
    )


@pytest.mark.django_db(transaction=True)
def test_the_receipt_is_issued_once(as_user, reseller, order, renderer):
    deliver(as_user, reseller, order)
    from apps.documents.facades import ReceiptFacade
    from core.container import container

    container.resolve(ReceiptFacade).delivered(order.pk)

    assert DeliveryReceipt.objects.count() == 1
    assert len(receipt_mails()) == 1


@pytest.mark.django_db
class TestDownloads:
    def test_client_and_back_office_download_the_same_receipt(
        self, as_user, shopper, manager, *, reseller, order, renderer
    ):
        deliver(as_user, reseller, order)

        mine = as_user(shopper).get(f"{MINE}{order.number}/receipt/")
        staff = as_user(manager).get(f"{BO}{order.pk}/receipt/")

        assert mine.status_code == 200
        assert mine["Content-Type"] == "application/pdf"
        assert f"recu-livraison-{order.number}.pdf" in mine["Content-Disposition"]
        assert staff.status_code == 200
        # orders delivered without a receipt yet (or before receipts existed) get one on download
        assert DeliveryReceipt.objects.filter(order_id=order.pk).count() == 1
        first, second = renderer.calls[-2][1], renderer.calls[-1][1]
        assert first["signature"] == second["signature"]

    def test_no_receipt_before_delivery(self, as_user, shopper, order, renderer):
        response = as_user(shopper).get(f"{MINE}{order.number}/receipt/")

        assert response.status_code == 409
        assert response.json()["code"] == "receipt_unavailable"

    def test_a_manager_confirmation_states_its_reason(
        self, as_user, manager, reseller, order, renderer
    ):
        for status in ("confirmed", "paid", "shipping"):
            as_user(reseller).post(f"{BO}{order.pk}/transition/", {"to": status})
        as_user(manager).post(
            f"{BO}{order.pk}/transition/",
            {"to": "delivered", "reason": "Client joint par téléphone"},
        )

        as_user(manager).get(f"{BO}{order.pk}/receipt/")

        receipt = DeliveryReceipt.objects.get(order_id=order.pk)
        assert receipt.payload["confirmation"] == (
            "Livraison confirmée sans code par un responsable : Client joint par téléphone"
        )

    def test_other_clients_cannot_read_it(self, as_user, reseller, order, renderer):
        from apps.accounts.tests.factories import UserFactory

        deliver(as_user, reseller, order)

        response = as_user(UserFactory.create()).get(f"{MINE}{order.number}/receipt/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestVerification:
    def test_a_genuine_receipt_verifies(self, api, as_user, manager, *, reseller, order, renderer):
        deliver(as_user, reseller, order)
        as_user(manager).get(f"{BO}{order.pk}/receipt/")
        receipt = DeliveryReceipt.objects.get()

        good = api.post(VERIFY, {"number": receipt.number.lower(), "signature": receipt.signature})
        forged = api.post(VERIFY, {"number": receipt.number, "signature": "0" * 64})

        assert good.json() == {
            "valid": True,
            "order_number": order.number,
            "delivered_at": receipt.payload["delivered_at"],
            "total": str(order.total),
        }
        assert forged.json()["valid"] is False
        assert forged.json()["order_number"] is None

    def test_a_receipt_edited_afterwards_no_longer_verifies(
        self, api, as_user, manager, *, reseller, order, renderer
    ):
        deliver(as_user, reseller, order)
        as_user(manager).get(f"{BO}{order.pk}/receipt/")
        receipt = DeliveryReceipt.objects.get()
        receipt.payload = {**receipt.payload, "total": "1.00"}
        receipt.save(update_fields=["payload"])

        response = api.post(VERIFY, {"number": receipt.number, "signature": receipt.signature})

        assert response.json()["valid"] is False


def test_queued_mail_keeps_its_attachments():
    from django.core.mail import EmailMultiAlternatives

    message = EmailMultiAlternatives(subject="S", body="B", to=["a@celebobo.test"])
    message.attach("recu.pdf", b"%PDF-1.7 \x00\xff", "application/pdf")

    rebuilt = build_message(serialize_message(message))

    assert rebuilt.attachments[0] == ("recu.pdf", b"%PDF-1.7 \x00\xff", "application/pdf")

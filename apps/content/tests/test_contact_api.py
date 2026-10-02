import pytest

from apps.content.models import ContactMessage

pytestmark = pytest.mark.django_db

CONTACT = "/api/v1/contact/"
INBOX = "/api/v1/bo/contact-messages/"
MESSAGE = {
    "name": " Aline   Mbuyi ",
    "email": "Aline@Example.com",
    "phone": "+243 81 234 5678",
    "subject": "order",
    "message": "Ma commande n'est pas encore arrivée.",
}


def send(api, capture, **overrides):
    with capture(execute=True):
        return api.post(CONTACT, {**MESSAGE, **overrides}, format="json")


def test_messages_are_stored_and_acknowledged(
    api, site, mailoutbox, django_capture_on_commit_callbacks
):
    response = send(api, django_capture_on_commit_callbacks)

    assert response.status_code == 202
    message = ContactMessage.objects.get()
    assert (message.name, message.email, message.status) == (
        "Aline Mbuyi",
        "aline@example.com",
        "new",
    )
    assert sorted(mail.to[0] for mail in mailoutbox) == [
        "aline@example.com",
        "support@celebobo.test",
    ]
    alert = next(mail for mail in mailoutbox if mail.to == ["support@celebobo.test"])
    assert "Ma commande n'est pas encore arrivée." in alert.body


def test_honeypot_submissions_are_quietly_filed_as_spam(
    api, site, mailoutbox, django_capture_on_commit_callbacks
):
    response = send(api, django_capture_on_commit_callbacks, website="https://spam.test")

    assert response.status_code == 202
    assert ContactMessage.objects.get().status == "spam"
    assert mailoutbox == []


def test_validation(api):
    response = api.post(CONTACT, {**MESSAGE, "subject": "nope", "message": "court"}, format="json")

    assert response.status_code == 400
    assert set(response.json()["errors"]) == {"subject", "message"}


def test_inbox_workflow(api, as_user, manager, django_capture_on_commit_callbacks):
    send(api, django_capture_on_commit_callbacks)
    send(
        api,
        django_capture_on_commit_callbacks,
        subject="product",
        message="Le Galaxy est-il dispo ?",
    )
    staff = as_user(manager)

    listing = staff.get(INBOX).json()
    message_id = listing["results"][0]["id"]
    handled = staff.patch(
        f"{INBOX}{message_id}/", {"status": "handled", "note": "Rappelée"}, format="json"
    )
    reopened = staff.patch(f"{INBOX}{message_id}/", {"status": "new"}, format="json")

    assert listing["meta"]["counts"] == {"new": 2, "handled": 0, "spam": 0}
    assert staff.get(INBOX, {"subject": "product"}).json()["meta"]["count"] == 1
    assert staff.get(INBOX, {"search": "galaxy"}).json()["meta"]["count"] == 1
    assert handled.json()["handled_by"] == "Joël Mpiana"
    assert handled.json()["note"] == "Rappelée"
    assert reopened.json()["handled_at"] is None
    assert staff.get(f"{INBOX}999999/").status_code == 404


def test_only_staff_read_the_inbox(as_user, reseller):
    assert as_user(reseller).get(INBOX).status_code == 403

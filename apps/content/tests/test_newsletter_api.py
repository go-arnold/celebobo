import pytest

from apps.content.models import Subscriber

pytestmark = pytest.mark.django_db

SUBSCRIBE = "/api/v1/newsletter/subscribe/"
UNSUBSCRIBE = "/api/v1/newsletter/unsubscribe/"
SUBSCRIBERS = "/api/v1/bo/newsletter/subscribers/"


def subscribe(api, capture, email="Grace@Example.com", source="footer"):
    with capture(execute=True):
        return api.post(SUBSCRIBE, {"email": email, "source": source}, format="json")


def test_subscribing_returns_the_welcome_code(
    api, site, mailoutbox, django_capture_on_commit_callbacks
):
    body = subscribe(api, django_capture_on_commit_callbacks).json()

    assert body == {
        "email": "grace@example.com",
        "code": "BIENVENUE10",
        "discount": 10,
        "already_subscribed": False,
    }
    (mail,) = mailoutbox
    subscriber = Subscriber.objects.get()
    assert "BIENVENUE10" in mail.body
    assert f"/newsletter/desinscription?token={subscriber.token}" in mail.body


def test_subscribing_twice_sends_nothing_new(
    api, site, mailoutbox, django_capture_on_commit_callbacks
):
    subscribe(api, django_capture_on_commit_callbacks)
    again = subscribe(api, django_capture_on_commit_callbacks, email="GRACE@example.com").json()

    assert again["already_subscribed"] is True
    assert len(mailoutbox) == 1
    assert Subscriber.objects.count() == 1


def test_unsubscribe_and_come_back(api, site, mailoutbox, django_capture_on_commit_callbacks):
    subscribe(api, django_capture_on_commit_callbacks)
    token = str(Subscriber.objects.get().token)

    assert api.post(UNSUBSCRIBE, {"token": token}, format="json").status_code == 204
    assert api.post(UNSUBSCRIBE, {"token": token}, format="json").status_code == 204
    assert not Subscriber.objects.get().is_active
    back = subscribe(api, django_capture_on_commit_callbacks).json()

    assert back["already_subscribed"] is False
    assert Subscriber.objects.get().is_active
    assert len(mailoutbox) == 2


def test_unknown_tokens(api):
    response = api.post(
        UNSUBSCRIBE, {"token": "00000000-0000-0000-0000-000000000000"}, format="json"
    )

    assert response.status_code == 404


def test_backoffice_listing_and_export(api, as_user, manager, django_capture_on_commit_callbacks):
    subscribe(api, django_capture_on_commit_callbacks, email="a@example.com")
    subscribe(api, django_capture_on_commit_callbacks, email="b@example.com")
    api.post(
        UNSUBSCRIBE,
        {"token": str(Subscriber.objects.get(email="b@example.com").token)},
        format="json",
    )
    staff = as_user(manager)

    active = staff.get(SUBSCRIBERS, {"active": "true"}).json()
    export = staff.get(f"{SUBSCRIBERS}export/")

    assert active["meta"]["count"] == 1
    assert staff.get(SUBSCRIBERS, {"search": "b@"}).json()["results"][0]["is_active"] is False
    lines = export.content.decode().lstrip("﻿").splitlines()
    assert lines[0] == "email;source;actif;inscrit le;désinscrit le"
    assert len(lines) == 3
    assert "attachment" in export["Content-Disposition"]


def test_only_staff_see_subscribers(as_user, reseller):
    assert as_user(reseller).get(SUBSCRIBERS).status_code == 403

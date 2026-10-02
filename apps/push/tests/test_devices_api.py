import pytest

from apps.accounts.tests.factories import UserFactory
from apps.push.models import PushSubscription
from apps.push.tests.conftest import device_payload

pytestmark = pytest.mark.django_db

DEVICES = "/api/v1/me/devices/"


@pytest.fixture
def client_api(api):
    user = UserFactory.create()
    api.force_authenticate(user)
    api.user = user
    return api


def test_public_key(api, settings):
    settings.PUSH = {"VAPID_PUBLIC_KEY": "BPublicKey", "VAPID_PRIVATE_KEY": "secret"}

    assert api.get("/api/v1/push/public-key/").json() == {
        "public_key": "BPublicKey",
        "enabled": True,
    }


def test_push_is_off_without_keys(api):
    assert api.get("/api/v1/push/public-key/").json()["enabled"] is False


def test_registering_and_listing_devices(client_api):
    created = client_api.post(DEVICES, device_payload(), format="json")
    again = client_api.post(DEVICES, device_payload(), format="json")

    assert created.status_code == 201
    assert again.json()["id"] == created.json()["id"]
    assert [device["user_agent"] for device in client_api.get(DEVICES).json()] == ["Firefox 140"]


def test_endpoints_must_be_https(client_api):
    response = client_api.post(
        DEVICES, {**device_payload(), "endpoint": "http://push.example.com/a"}, format="json"
    )

    assert response.status_code == 400
    assert "endpoint" in response.json()["errors"]


def test_a_browser_moves_to_whoever_signs_in(api, client_api):
    client_api.post(DEVICES, device_payload(), format="json")
    other = UserFactory.create()
    api.force_authenticate(other)

    api.post(DEVICES, device_payload(), format="json")

    assert PushSubscription.objects.get().user_id == other.pk


def test_device_limit(client_api, settings):
    settings.PUSH = {"MAX_DEVICES": 2}
    client_api.post(DEVICES, device_payload("a"), format="json")
    client_api.post(DEVICES, device_payload("b"), format="json")

    refused = client_api.post(DEVICES, device_payload("c"), format="json")
    refreshed = client_api.post(DEVICES, device_payload("b"), format="json")

    assert refused.status_code == 422
    assert refused.json()["code"] == "too_many_devices"
    assert refreshed.status_code == 201


def test_removing_a_device(api, client_api):
    device_id = client_api.post(DEVICES, device_payload(), format="json").json()["id"]
    api.force_authenticate(UserFactory.create())

    assert api.delete(f"{DEVICES}{device_id}/").status_code == 404
    api.force_authenticate(client_api.user)
    assert api.delete(f"{DEVICES}{device_id}/").status_code == 204
    assert not PushSubscription.objects.exists()


def test_anonymous_visitors_have_no_devices(api):
    assert api.get(DEVICES).status_code in (401, 403)

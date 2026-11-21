import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminFactory, ManagerFactory
from apps.loyalty.domain.events import LoyaltySettingsChanged

pytestmark = pytest.mark.django_db

SETTINGS = "/api/v1/bo/loyalty/settings/"
PUBLIC = "/api/v1/settings/public/"


@pytest.fixture
def admin_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(AdminFactory.create())
    return api


def test_programmes_start_disabled_with_the_approved_rules():
    programmes = APIClient().get(PUBLIC).json()["programmes"]

    assert programmes == {
        "points": {
            "enabled": False,
            "percent": "1.00",
            "validity_months": 12,
            "referral_percent": "0.30",
            "referral_months": 12,
        },
        "app_links": {"app_store": "", "play_store": ""},
    }


def test_admin_edits_every_rule(admin_api, published_events):
    response = admin_api.patch(
        SETTINGS,
        {
            "points_enabled": True,
            "points_percent": "5",
            "points_validity_months": 6,
            "referral_percent": "0.50",
            "play_store_url": "https://play.google.com/store/apps/details?id=cd.celebobo",
        },
        format="json",
    )

    body = response.json()
    assert "membership" not in body
    assert body["points"]["percent"] == "5.00"
    assert body["points"]["validity_months"] == 6
    assert body["points"]["referral_percent"] == "0.50"
    assert body["app_links"]["play_store"].endswith("cd.celebobo")
    assert len(published_events.of_type(LoyaltySettingsChanged)) == 1


def test_public_settings_follow_the_change(admin_api, django_capture_on_commit_callbacks):
    APIClient().get(PUBLIC)
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        admin_api.patch(SETTINGS, {"points_enabled": True}, format="json")

    assert APIClient().get(PUBLIC).json()["programmes"]["points"]["enabled"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"points_percent": "0"},
        {"points_validity_months": 0},
        {"referral_percent": "0"},
        {"referral_months": 0},
        {"app_store_url": "pas-une-adresse"},
    ],
)
def test_rejects_invalid_rules(admin_api, payload):
    assert admin_api.patch(SETTINGS, payload, format="json").status_code == 400


def test_only_admins_manage():
    api = APIClient()
    api.force_authenticate(ManagerFactory.create())

    assert api.get(SETTINGS).status_code == 403


@pytest.mark.parametrize(
    "path",
    ["/api/v1/me/membership/", "/api/v1/bo/membership/requests/", "/api/v1/bo/memberships/"],
)
def test_the_paid_membership_is_gone(admin_api, path):
    assert admin_api.get(path).status_code == 404

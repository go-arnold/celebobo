import pytest
from django.db import transaction
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminFactory, ManagerFactory

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
        "cashback": {
            "enabled": False,
            "members_only": True,
            "percent": "3.00",
            "max_share": 50,
            "min_balance": "1.00",
            "validity_months": 12,
        },
        "app_links": {"app_store": "", "play_store": ""},
    }


def test_admin_edits_cashback_rules(admin_api, published_events):
    response = admin_api.patch(
        SETTINGS,
        {
            "cashback_enabled": True,
            "cashback_percent": "5",
            "cashback_max_share": 30,
            "play_store_url": "https://play.google.com/store/apps/details?id=cd.celebobo",
        },
        format="json",
    )

    body = response.json()
    assert body["cashback"]["percent"] == "5.00"
    assert body["cashback"]["max_share"] == 30
    assert body["app_links"]["play_store"].endswith("cd.celebobo")


def test_public_settings_follow_the_change(admin_api, django_capture_on_commit_callbacks):
    APIClient().get(PUBLIC)
    with django_capture_on_commit_callbacks(execute=True), transaction.atomic():
        admin_api.patch(SETTINGS, {"cashback_enabled": True}, format="json")

    assert APIClient().get(PUBLIC).json()["programmes"]["cashback"]["enabled"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"cashback_percent": "0"},
        {"cashback_max_share": 101},
        {"app_store_url": "pas-une-adresse"},
    ],
)
def test_rejects_invalid_rules(admin_api, payload):
    assert admin_api.patch(SETTINGS, payload, format="json").status_code == 400


def test_only_admins_manage():
    api = APIClient()
    api.force_authenticate(ManagerFactory.create())

    assert api.get(SETTINGS).status_code == 403

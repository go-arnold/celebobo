import pytest

from apps.accounts.tests.factories import UserFactory
from apps.resellers.conf import ResellerSettings
from apps.resellers.services.referrals import ReferralKitBuilder

pytestmark = pytest.mark.django_db

REFERRAL = "/api/v1/bo/me/referral/"
INVITEES = "/api/v1/bo/me/invitees/"


class FakeQr:
    def svg_data_uri(self, content: str, *, scale: int) -> str:
        return f"qr:{content}:{scale}"


def test_kit_builder_formats_links_and_share_text():
    kit = ReferralKitBuilder(FakeQr(), ResellerSettings(), base_url="https://celebobo.cd/").build(
        "4821"
    )

    assert kit.link == "https://celebobo.cd/inscription?code=4821"
    assert kit.qr_svg == "qr:https://celebobo.cd/inscription?code=4821:8"
    assert "4821" in kit.share_text
    assert kit.whatsapp_url.startswith("https://wa.me/?text=Rejoins-moi%20sur%20Celebobo")


def test_resellers_get_their_referral_kit(as_user, reseller):
    body = as_user(reseller).get(REFERRAL).json()

    assert body["code"] == "4821"
    assert body["link"].endswith("/inscription?code=4821")
    assert body["qr_svg"].startswith("data:image/svg+xml")


def test_resellers_see_their_invitees(as_user, reseller, shopper):
    shopper.invited_by = reseller
    shopper.save(update_fields=["invited_by"])
    UserFactory.create()

    body = as_user(reseller).get(INVITEES).json()

    assert body["meta"]["count"] == 1
    assert body["meta"]["summary"]["invited_count"] == 1
    assert body["results"][0]["email"] == shopper.email


def test_staff_without_a_code(as_user, manager):
    assert as_user(manager).get(REFERRAL).status_code == 404


def test_clients_have_no_referral_kit(as_user, shopper):
    assert as_user(shopper).get(REFERRAL).status_code == 403

from datetime import timedelta

import pytest
from django.utils import timezone

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
    shopper.invited_at = timezone.now() - timedelta(days=30)
    shopper.save(update_fields=["invited_by", "invited_at"])
    UserFactory.create()

    body = as_user(reseller).get(INVITEES).json()

    assert body["meta"]["count"] == 1
    assert body["meta"]["summary"] == {"code": "4821", "invited_count": 1}
    (row,) = body["results"]
    assert row["name"] == "Aline Mbuyi"
    assert row["referral_active"] is True
    assert row["referral_ends_at"] is not None


def test_invitees_show_no_email_nor_purchases(as_user, reseller, shopper, phone, place_order):
    shopper.invited_by = reseller
    shopper.invited_at = timezone.now()
    shopper.save(update_fields=["invited_by", "invited_at"])
    place_order(shopper, phone)

    body = as_user(reseller).get(INVITEES).json()

    # privacy policy §4: the reseller sees neither the e-mail nor the purchase history
    assert set(body["results"][0]) == {
        "id",
        "name",
        "joined_at",
        "referral_ends_at",
        "referral_active",
    }
    assert "orders_total" not in body["meta"]["summary"]


def test_the_referral_period_ends_after_twelve_months(as_user, reseller):
    invited_at = timezone.now() - timedelta(days=400)
    UserFactory.create(invited_by=reseller, invited_at=invited_at, first_name="", last_name="")
    UserFactory.create(invited_by=reseller, invited_at=None)

    rows = as_user(reseller).get(INVITEES).json()["results"]

    by_period = {row["referral_ends_at"] is None: row for row in rows}
    expired = by_period[False]
    assert expired["referral_active"] is False
    assert expired["referral_ends_at"].startswith(f"{invited_at.year + 1}-")
    # a nameless account shows no e-mail in its place
    assert expired["name"] == "Client sans nom"
    assert by_period[True]["referral_active"] is False


def test_staff_without_a_code(as_user, manager):
    assert as_user(manager).get(REFERRAL).status_code == 404


def test_clients_have_no_referral_kit(as_user, shopper):
    assert as_user(shopper).get(REFERRAL).status_code == 403

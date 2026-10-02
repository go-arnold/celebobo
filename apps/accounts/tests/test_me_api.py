import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.domain.events import AccountDeleted, ProfileUpdated, ReferralAttached
from apps.accounts.models import Address, User
from apps.accounts.tests.factories import AddressFactory, ResellerFactory, UserFactory

pytestmark = pytest.mark.django_db

ME = "/api/v1/me/"


class TestProfile:
    def test_requires_authentication(self, api: APIClient):
        response = api.get(ME)

        assert response.status_code == 401
        assert response.json()["code"] == "not_authenticated"

    def test_client_profile(self, as_user, client_user):
        body = as_user(client_user).get(ME).json()

        assert body["email"] == "aline@celebobo.test"
        assert body["role"] == "client"
        assert body["reseller"] is None
        assert body["email_verified"] is True
        assert "addresses.manage" in body["permissions"]
        assert "users.manage" not in body["permissions"]

    def test_reseller_profile_includes_program_details(self, as_user, reseller):
        UserFactory.create_batch(2, invited_by=reseller)

        body = as_user(reseller).get(ME).json()

        assert body["reseller"] == {
            "referral_code": "4821",
            "availability": "offline",
            "commission_rate": "0.070",
            "invited_count": 2,
        }
        assert "availability.update" in body["permissions"]

    def test_partial_update(self, as_user, client_user, published_events):
        response = as_user(client_user).patch(
            ME, {"first_name": "  Aline  Grâce ", "phone_number": "+243 99 000 0000"}
        )

        assert response.status_code == 200
        assert response.json()["first_name"] == "Aline Grâce"
        assert response.json()["last_name"] == "Mbuyi"
        assert published_events.single(ProfileUpdated).fields == ("first_name", "phone_number")

    def test_email_cannot_be_changed(self, as_user, client_user):
        as_user(client_user).patch(ME, {"email": "other@celebobo.test"})

        client_user.refresh_from_db()
        assert client_user.email == "aline@celebobo.test"

    def test_phone_must_be_unique(self, as_user, client_user):
        UserFactory.create(phone_number="+243 99 000 0000")

        response = as_user(client_user).patch(ME, {"phone_number": "+243 99 000 0000"})

        assert response.status_code == 400
        assert response.json()["code"] == "phone_already_used"

    def test_referral_can_be_attached_once(self, as_user, client_user, reseller, published_events):
        api = as_user(client_user)

        first = api.patch(ME, {"referral_code": "4821"})
        second = api.patch(ME, {"referral_code": ResellerFactory.create().referral_code})

        assert first.json()["invited_by_code"] == "4821"
        assert published_events.single(ReferralAttached).reseller_id == reseller.pk
        assert second.status_code == 422
        assert second.json()["code"] == "referral_already_set"

    def test_reseller_cannot_refer_themselves(self, as_user, reseller):
        response = as_user(reseller).patch(ME, {"referral_code": "4821"})

        assert response.json()["code"] == "self_referral"


class TestAccountDeletion:
    def test_client_account_is_anonymized_and_tokens_revoked(
        self, as_user, client_user, published_events
    ):
        AddressFactory.create(user=client_user)
        RefreshToken.for_user(client_user)

        response = as_user(client_user).delete(ME)

        assert response.status_code == 204
        user = User.objects.get(pk=client_user.pk)
        assert user.is_active is False
        assert user.email == f"deleted-{user.pk}@deleted.invalid"
        assert user.first_name == ""
        assert not user.has_usable_password()
        assert not Address.objects.filter(user=user).exists()
        assert all(
            hasattr(token, "blacklistedtoken")
            for token in OutstandingToken.objects.filter(user=user)
        )
        assert published_events.single(AccountDeleted).user_id == user.pk

    def test_reseller_accounts_cannot_self_delete(self, as_user, reseller):
        response = as_user(reseller).delete(ME)

        assert response.status_code == 422
        assert response.json()["code"] == "staff_account_deletion"

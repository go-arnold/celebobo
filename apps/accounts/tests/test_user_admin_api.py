import pytest
from allauth.account.models import EmailAddress
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.domain.events import (
    PasswordResetRequested,
    UserActivationChanged,
    UserCreated,
    UserEdited,
)
from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

USERS = "/api/v1/bo/users/"
NEW_USER = {
    "first_name": " Sarah ",
    "last_name": "Kalala",
    "email": "Sarah.Kalala@Celebobo.test",
    "phone_number": "+243 81 777 0000",
    "role": "manager",
}


class TestDirectory:
    def test_lists_users_with_counts_and_inviter(self, as_user, admin_user, reseller, client_user):
        client_user.invited_by = reseller
        client_user.save(update_fields=["invited_by"])
        EmailAddress.objects.filter(user=client_user).update(verified=True)

        body = as_user(admin_user).get(USERS).json()

        assert body["meta"]["count"] == 3
        assert body["meta"]["counts"] == {"client": 1, "reseller": 1, "manager": 0, "admin": 1}
        row = next(item for item in body["results"] if item["id"] == client_user.pk)
        assert row["invited_by"] == {
            "id": reseller.pk,
            "name": reseller.get_full_name(),
            "referral_code": "4821",
        }
        assert row["email_verified"] is True
        assert row["role"] == "client"

    def test_filters(self, as_user, admin_user, reseller, client_user):
        UserFactory.create(is_active=False)
        api = as_user(admin_user)

        assert api.get(USERS, {"role": "reseller"}).json()["meta"]["count"] == 1
        assert api.get(USERS, {"search": "aline@"}).json()["meta"]["count"] == 1
        assert api.get(USERS, {"search": "4821"}).json()["results"][0]["id"] == reseller.pk
        assert api.get(USERS, {"active": "false"}).json()["meta"]["count"] == 1

    def test_deleted_accounts_are_hidden(self, as_user, admin_user, client_user):
        as_user(client_user).delete("/api/v1/me/")

        api = as_user(admin_user)

        assert api.get(USERS, {"role": "client"}).json()["meta"]["count"] == 0
        assert api.get(f"{USERS}{client_user.pk}/").status_code == 404

    def test_managers_read_only(self, as_user, manager, client_user):
        api = as_user(manager)

        assert api.get(USERS).status_code == 200
        assert api.get(f"{USERS}{client_user.pk}/").status_code == 200
        assert api.post(USERS, NEW_USER, format="json").status_code == 403
        assert api.post(f"{USERS}{client_user.pk}/deactivate/").status_code == 403

    def test_clients_and_resellers_have_no_access(self, as_user, reseller):
        assert as_user(reseller).get(USERS).status_code == 403


class TestCreation:
    def test_admins_create_accounts_without_password(self, as_user, admin_user, published_events):
        response = as_user(admin_user).post(USERS, NEW_USER, format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "sarah.kalala@celebobo.test"
        assert body["first_name"] == "Sarah"
        assert body["role"] == "manager"
        assert body["email_verified"] is True
        user = User.objects.get(pk=body["id"])
        assert user.is_staff is True
        assert not user.has_usable_password()
        assert published_events.single(UserCreated).role == "manager"

    def test_resellers_get_a_referral_code(self, as_user, admin_user):
        body = as_user(admin_user).post(USERS, {**NEW_USER, "role": "reseller"}, format="json")

        assert len(body.json()["referral_code"]) == 4

    def test_invitation_email(
        self, as_user, admin_user, mailoutbox, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            as_user(admin_user).post(USERS, NEW_USER, format="json")

        (mail,) = mailoutbox
        assert mail.to == ["sarah.kalala@celebobo.test"]
        assert "/reinitialiser-mot-de-passe?uid=" in mail.body

    def test_rejects_taken_email_and_phone(self, as_user, admin_user, client_user):
        api = as_user(admin_user)
        client_user.phone_number = "+243 81 777 0000"
        client_user.save(update_fields=["phone_number"])

        email = api.post(USERS, {**NEW_USER, "email": "ALINE@celebobo.test"}, format="json")
        phone = api.post(USERS, NEW_USER, format="json")

        assert email.status_code == 400
        assert "email" in email.json()["errors"]
        assert phone.status_code == 400
        assert "phone_number" in phone.json()["errors"]


class TestEditing:
    def test_edits_identity_fields(self, as_user, admin_user, client_user, published_events):
        response = as_user(admin_user).patch(
            f"{USERS}{client_user.pk}/",
            {"first_name": "Aline-Grâce", "email": "Aline.New@celebobo.test"},
            format="json",
        )

        assert response.status_code == 200
        assert response.json()["first_name"] == "Aline-Grâce"
        assert response.json()["email"] == "aline.new@celebobo.test"
        assert list(
            EmailAddress.objects.filter(user=client_user).values_list("email", "verified")
        ) == [("aline.new@celebobo.test", True)]
        assert set(published_events.single(UserEdited).fields) == {"first_name", "email"}

    def test_unchanged_values_publish_nothing(
        self, as_user, admin_user, client_user, published_events
    ):
        as_user(admin_user).patch(
            f"{USERS}{client_user.pk}/", {"first_name": "Aline"}, format="json"
        )

        assert not [e for e in published_events.events if isinstance(e, UserEdited)]

    def test_rejects_an_email_in_use(self, as_user, admin_user, client_user, reseller):
        response = as_user(admin_user).patch(
            f"{USERS}{client_user.pk}/", {"email": reseller.email}, format="json"
        )

        assert response.status_code == 400

    def test_clears_the_phone(self, as_user, admin_user, client_user):
        client_user.phone_number = "+243 81 000 0009"
        client_user.save(update_fields=["phone_number"])

        response = as_user(admin_user).patch(
            f"{USERS}{client_user.pk}/", {"phone_number": None}, format="json"
        )

        assert response.json()["phone_number"] is None


class TestAccess:
    def test_deactivation_revokes_tokens(self, as_user, admin_user, reseller, published_events):
        RefreshToken.for_user(reseller)
        api = as_user(admin_user)

        response = api.post(f"{USERS}{reseller.pk}/deactivate/")
        api.post(f"{USERS}{reseller.pk}/deactivate/")

        assert response.json()["is_active"] is False
        assert not OutstandingToken.objects.filter(
            user=reseller, blacklistedtoken__isnull=True
        ).exists()
        assert published_events.single(UserActivationChanged).active is False

    def test_reactivation(self, as_user, admin_user):
        dormant = UserFactory.create(is_active=False)

        assert as_user(admin_user).post(f"{USERS}{dormant.pk}/activate/").json()["is_active"]

    def test_admins_cannot_lock_themselves_out(self, as_user, admin_user):
        response = as_user(admin_user).post(f"{USERS}{admin_user.pk}/deactivate/")

        assert response.status_code == 403
        assert response.json()["code"] == "own_account_deactivation"

    def test_password_reset_email(
        self,
        as_user,
        admin_user,
        client_user,
        mailoutbox,
        django_capture_on_commit_callbacks,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = as_user(admin_user).post(f"{USERS}{client_user.pk}/send-password-reset/")

        assert response.status_code == 202
        (mail,) = mailoutbox
        assert mail.to == [client_user.email]
        assert "/reinitialiser-mot-de-passe?uid=" in mail.body

    def test_no_reset_for_inactive_accounts(self, as_user, admin_user, published_events):
        dormant = UserFactory.create(is_active=False)

        response = as_user(admin_user).post(f"{USERS}{dormant.pk}/send-password-reset/")

        assert response.status_code == 422
        assert not [e for e in published_events.events if isinstance(e, PasswordResetRequested)]

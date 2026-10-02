import re
from urllib.parse import parse_qs, urlparse

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.domain.events import UserRegistered
from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory

pytestmark = pytest.mark.django_db

REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
ME = "/api/v1/me/"
PAYLOAD = {
    "first_name": "Aline",
    "last_name": "Mbuyi",
    "email": "Aline@Celebobo.test",
    "password": "Kinshasa-2026!",
    "phone_number": "+243 81 234 5678",
}


def link_in(message: mail.EmailMessage) -> str:
    match = re.search(r"https://app\.test/\S+", str(message.body))
    assert match, message.body
    return match.group(0)


class TestRegistration:
    def test_creates_unverified_client_and_sends_frontend_link(
        self, api: APIClient, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = api.post(REGISTER, PAYLOAD)

        assert response.status_code == 201
        assert response.json()["verification_required"] is True
        assert "cb_access" not in response.cookies
        user = User.objects.get(email="aline@celebobo.test")
        assert user.role == "client"
        assert EmailAddress.objects.get(user=user).verified is False
        (message,) = mail.outbox
        assert message.to == ["aline@celebobo.test"]
        assert message.subject == "Celebobo — Confirmez votre adresse e-mail"
        assert link_in(message).startswith("https://app.test/verifier-email/")

    def test_publishes_user_registered(self, api: APIClient, published_events):
        api.post(REGISTER, PAYLOAD)

        event = published_events.single(UserRegistered)
        assert event.user_id == User.objects.get().pk

    def test_referral_code_links_inviter(self, api: APIClient, reseller):
        response = api.post(REGISTER, {**PAYLOAD, "referral_code": "4821"})

        assert response.status_code == 201
        assert User.objects.get(email="aline@celebobo.test").invited_by == reseller

    @pytest.mark.parametrize(
        ("overrides", "field", "code"),
        [
            ({"referral_code": "9999"}, "referral_code", "unknown_referral_code"),
            ({"referral_code": "12a"}, "referral_code", "validation_failed"),
            ({"password": "password"}, "password", "weak_password"),
            ({"email": "not-an-email"}, "email", "validation_failed"),
        ],
    )
    def test_rejections_are_field_errors(self, api: APIClient, overrides, field, code):
        response = api.post(REGISTER, {**PAYLOAD, **overrides})

        assert response.status_code == 400
        assert response.json()["code"] == code
        assert field in response.json()["errors"]

    def test_duplicate_email_is_case_insensitive(self, api: APIClient):
        UserFactory.create(email="aline@celebobo.test")

        response = api.post(REGISTER, PAYLOAD)

        assert response.status_code == 400
        assert response.json()["code"] == "email_already_used"

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
    def test_signs_in_immediately_without_verification(self, api: APIClient):
        response = api.post(REGISTER, PAYLOAD)

        assert response.status_code == 201
        assert response.json()["verification_required"] is False
        assert response.cookies["cb_access"].value
        assert response.cookies["cb_refresh"]["httponly"]


class TestSessionFlow:
    def register_and_verify(self, api: APIClient, capture) -> None:
        with capture(execute=True):
            api.post(REGISTER, PAYLOAD)
        key = link_in(mail.outbox[-1]).rsplit("/", 1)[-1]
        assert api.post("/api/v1/auth/email/verify/", {"key": key}).status_code == 200

    def test_unverified_users_cannot_log_in(self, api: APIClient):
        api.post(REGISTER, PAYLOAD)

        response = api.post(LOGIN, {"email": PAYLOAD["email"], "password": PAYLOAD["password"]})

        assert response.status_code == 400

    def test_verify_login_profile_logout(self, api: APIClient, django_capture_on_commit_callbacks):
        self.register_and_verify(api, django_capture_on_commit_callbacks)

        login = api.post(LOGIN, {"email": "aline@celebobo.test", "password": PAYLOAD["password"]})

        assert login.status_code == 200
        assert login.json()["user"]["email"] == "aline@celebobo.test"
        assert login.json()["user"]["email_verified"] is True
        assert login.cookies["cb_access"]["httponly"]
        assert api.get(ME).json()["first_name"] == "Aline"

        assert api.post("/api/v1/auth/logout/").status_code == 200
        api.cookies.pop("cb_access", None)
        assert api.get(ME).status_code == 401

    def test_cookie_auth_enforces_csrf(self):
        user = UserFactory.create()
        api = APIClient(enforce_csrf_checks=True)
        api.post(LOGIN, {"email": user.email, "password": DEFAULT_PASSWORD})

        rejected = api.patch(ME, {"first_name": "Jean"})
        api.get("/api/v1/auth/csrf/")
        accepted = api.patch(
            ME, {"first_name": "Jean"}, HTTP_X_CSRFTOKEN=api.cookies["csrftoken"].value
        )

        assert rejected.status_code == 403
        assert accepted.status_code == 200

    def test_refresh_rotates_tokens(self, api: APIClient):
        user = UserFactory.create()
        api.post(LOGIN, {"email": user.email, "password": DEFAULT_PASSWORD})
        first_refresh = api.cookies["cb_refresh"].value

        response = api.post("/api/v1/auth/token/refresh/")

        assert response.status_code == 200
        assert api.cookies["cb_refresh"].value != first_refresh

    def test_password_reset_uses_frontend_link(self, api: APIClient):
        user = UserFactory.create()

        assert api.post("/api/v1/auth/password/reset/", {"email": user.email}).status_code == 200

        (message,) = mail.outbox
        url = urlparse(link_in(message))
        assert url.path == "/reinitialiser-mot-de-passe"
        params = parse_qs(url.query)
        confirm = api.post(
            "/api/v1/auth/password/reset/confirm/",
            {
                "uid": params["uid"][0],
                "token": params["token"][0],
                "new_password1": "Nouveau-mot-2026!",
                "new_password2": "Nouveau-mot-2026!",
            },
        )
        assert confirm.status_code == 200
        login = api.post(LOGIN, {"email": user.email, "password": "Nouveau-mot-2026!"})
        assert login.status_code == 200

    def test_password_reset_does_not_leak_unknown_emails(self, api: APIClient):
        response = api.post("/api/v1/auth/password/reset/", {"email": "nobody@celebobo.test"})

        assert response.status_code == 200
        assert mail.outbox == []


class TestReferralValidation:
    def test_valid_code(self, api: APIClient, reseller):
        response = api.get("/api/v1/auth/referral-codes/4821/validate/")

        assert response.json() == {"valid": True, "reseller_first_name": "Patrick"}

    def test_unknown_code(self, api: APIClient):
        assert api.get("/api/v1/auth/referral-codes/0000/validate/").json() == {
            "valid": False,
            "reseller_first_name": None,
        }

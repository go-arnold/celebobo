import pytest
from axes.models import AccessAttempt

from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.media.models import UploadedMedia

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"


def attempt(api, email, password):
    return api.post(LOGIN, {"email": email, "password": password}, format="json")


class TestLoginLockout:
    def test_repeated_failures_lock_the_account_for_that_address(self, api, settings):
        settings.AXES_FAILURE_LIMIT = 3
        user = UserFactory.create()

        failures = [attempt(api, user.email, "mauvais-mot").status_code for _ in range(3)]
        locked = attempt(api, user.email, DEFAULT_PASSWORD)

        assert failures == [400, 400, 429]
        assert locked.status_code == 429
        assert locked.json()["code"] == "too_many_login_attempts"
        assert AccessAttempt.objects.get().username == user.email

    def test_a_successful_login_resets_the_counter(self, api, settings):
        settings.AXES_FAILURE_LIMIT = 3
        user = UserFactory.create()
        attempt(api, user.email, "mauvais-mot")
        attempt(api, user.email, "mauvais-mot")

        assert attempt(api, user.email, DEFAULT_PASSWORD).status_code == 200
        user.refresh_from_db()
        assert user.last_login is not None
        assert attempt(api, user.email, "mauvais-mot").status_code == 400
        assert attempt(api, user.email, "mauvais-mot").status_code == 400

    def test_other_accounts_are_not_affected(self, api, settings):
        settings.AXES_FAILURE_LIMIT = 2
        victim, other = UserFactory.create(), UserFactory.create()
        for _ in range(2):
            attempt(api, victim.email, "mauvais-mot")

        assert attempt(api, other.email, DEFAULT_PASSWORD).status_code == 200


def test_responses_carry_a_content_security_policy(api):
    response = api.get("/health/live/")

    policy = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy


class TestAvatars:
    def upload(self, owner, purpose="avatar"):
        return UploadedMedia.objects.create(
            owner=owner,
            purpose=purpose,
            public_id=f"celebobo/avatars/{owner.pk}-{purpose}",
            url=f"https://res.cloudinary.com/demo/image/upload/v1/{owner.pk}-{purpose}.jpg",
            format="jpg",
            bytes=1000,
        )

    def test_avatars_come_from_the_users_own_uploads(self, as_user, client_user):
        mine = self.upload(client_user)
        theirs = self.upload(UserFactory.create())
        attachment = self.upload(client_user, "message_attachment")
        api = as_user(client_user)

        accepted = api.patch("/api/v1/me/", {"avatar_upload_id": mine.pk}, format="json")
        foreign = api.patch("/api/v1/me/", {"avatar_upload_id": theirs.pk}, format="json")
        wrong_kind = api.patch("/api/v1/me/", {"avatar_upload_id": attachment.pk}, format="json")
        cleared = api.patch("/api/v1/me/", {"avatar_upload_id": None}, format="json")

        assert accepted.json()["avatar"] == mine.url
        assert foreign.status_code == 400
        assert foreign.json()["code"] == "invalid_avatar"
        assert wrong_kind.status_code == 400
        assert cleared.json()["avatar"] == ""

    def test_plain_urls_are_ignored(self, as_user, client_user):
        response = as_user(client_user).patch(
            "/api/v1/me/", {"avatar": "https://evil.test/a.jpg"}, format="json"
        )

        assert response.json()["avatar"] == ""

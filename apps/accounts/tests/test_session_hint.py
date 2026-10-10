import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, ManagerFactory, UserFactory

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/token/refresh/"
HINT = "cb_session"


def login(api: APIClient, user: User):
    return api.post(LOGIN, {"email": user.email, "password": DEFAULT_PASSWORD})


def is_cleared(response) -> bool:
    return response.cookies[HINT].value == "" and response.cookies[HINT]["max-age"] == 0


class TestSessionHint:
    def test_login_sets_role_cookie_like_the_refresh_cookie(self, api: APIClient):
        response = login(api, ManagerFactory.create())

        hint = response.cookies[HINT]
        assert hint.value == "manager"
        assert hint["httponly"]
        assert hint["path"] == "/"
        assert hint["samesite"] == response.cookies["cb_refresh"]["samesite"]
        assert hint["secure"] == response.cookies["cb_refresh"]["secure"]
        assert hint["max-age"] == 14 * 24 * 3600

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="none")
    def test_registration_that_signs_in_sets_it(self, api: APIClient):
        response = api.post(
            "/api/v1/auth/register/",
            {
                "first_name": "Aline",
                "last_name": "Mbuyi",
                "email": "aline@celebobo.test",
                "password": "Kinshasa-2026!",
                "phone_number": "+243 81 234 5678",
            },
        )

        assert response.cookies[HINT].value == "client"

    def test_refresh_renews_it(self, api: APIClient):
        login(api, UserFactory.create())

        response = api.post(REFRESH)

        assert response.status_code == 200
        assert response.cookies[HINT].value == "client"

    def test_logout_clears_it(self, api: APIClient):
        login(api, UserFactory.create())

        response = api.post("/api/v1/auth/logout/")

        assert is_cleared(response)

    def test_refused_refresh_clears_it(self, api: APIClient):
        login(api, UserFactory.create())
        api.cookies["cb_refresh"] = "not-a-token"

        response = api.post(REFRESH)

        assert response.status_code == 401
        assert is_cleared(response)

    def test_deactivated_account_loses_it_on_refresh(self, api: APIClient):
        user = UserFactory.create()
        login(api, user)
        User.objects.filter(pk=user.pk).update(is_active=False)

        response = api.post(REFRESH)

        assert response.status_code == 401
        assert is_cleared(response)

    def test_role_change_is_picked_up_on_next_request(self, api: APIClient):
        user = UserFactory.create()
        login(api, user)
        User.objects.filter(pk=user.pk).update(role="reseller")

        response = api.get("/api/v1/me/")

        assert response.cookies[HINT].value == "reseller"

    def test_unchanged_role_is_not_resent(self, api: APIClient):
        login(api, UserFactory.create())

        assert HINT not in api.get("/api/v1/me/").cookies

    def test_anonymous_requests_do_not_touch_it(self, api: APIClient):
        api.cookies[HINT] = "client"

        assert HINT not in api.get("/api/v1/categories/").cookies

from collections.abc import Callable
from http import HTTPStatus

from dj_rest_auth.app_settings import api_settings as auth_settings
from django.http import HttpRequest, HttpResponseBase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User

SESSION_HINT_COOKIE = "cb_session"
REFRESH_URL_NAME = "token-refresh"

type Handler = Callable[[HttpRequest], HttpResponseBase]


# `cb_session` holds the role, never a credential: it follows the refresh cookie so the Next
# server can route a visitor without calling the API
def session_hint_middleware(get_response: Handler) -> Handler:
    def middleware(request: HttpRequest) -> HttpResponseBase:
        response = get_response(request)
        if request.path.startswith("/api/"):
            _sync(request, response)
        return response

    return middleware


def _sync(request: HttpRequest, response: HttpResponseBase) -> None:
    current = request.COOKIES.get(SESSION_HINT_COOKIE)
    issued = response.cookies.get(auth_settings.JWT_AUTH_REFRESH_COOKIE)
    if issued is not None:
        role = _role_from_refresh(issued.value)
        if role:
            _set(response, role)
        elif current:
            _clear(response)
        return
    match = request.resolver_match
    if (
        match
        and match.url_name == REFRESH_URL_NAME
        and response.status_code == HTTPStatus.UNAUTHORIZED
    ):
        if current:
            _clear(response)
        return
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and current != user.role:
        _set(response, user.role)


def _role_from_refresh(value: str) -> str | None:
    if not value:
        return None
    try:
        user_id = RefreshToken(value)[jwt_settings.USER_ID_CLAIM]  # type: ignore[arg-type]
    except (TokenError, KeyError):
        return None
    return User.objects.filter(pk=user_id, is_active=True).values_list("role", flat=True).first()


def _set(response: HttpResponseBase, role: str) -> None:
    response.set_cookie(
        SESSION_HINT_COOKIE,
        role,
        max_age=int(jwt_settings.REFRESH_TOKEN_LIFETIME.total_seconds()),
        secure=auth_settings.JWT_AUTH_SECURE,
        httponly=True,
        samesite=auth_settings.JWT_AUTH_SAMESITE,
        domain=auth_settings.JWT_AUTH_COOKIE_DOMAIN,
    )


def _clear(response: HttpResponseBase) -> None:
    response.delete_cookie(
        SESSION_HINT_COOKIE,
        samesite=auth_settings.JWT_AUTH_SAMESITE,
        domain=auth_settings.JWT_AUTH_COOKIE_DOMAIN,
    )

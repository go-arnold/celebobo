from typing import Any

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from core.api.throttling import SsrAwareAnonRateThrottle, SsrAwareScopedRateThrottle

SECRET = "ssr-secret-for-tests-7f3a9c"
LIMIT = 60


class AnonLimit(SsrAwareAnonRateThrottle):
    rate = f"{LIMIT}/min"


class ScopedLimit(SsrAwareScopedRateThrottle):
    THROTTLE_RATES = {"search": f"{LIMIT}/min"}


class PublicView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (AnonLimit, ScopedLimit)
    throttle_scope = "search"

    def get(self, request: Request) -> Response:
        return Response({"ok": True})


@pytest.fixture(autouse=True)
def ssr_secret():
    cache.clear()
    with override_settings(CORE={"SSR_SHARED_SECRET": SECRET}):
        yield
    cache.clear()


def statuses(count: int, **headers: Any) -> list[int]:
    view = PublicView.as_view()
    factory = APIRequestFactory()
    return [view(factory.get("/", **headers)).status_code for _ in range(count)]


def test_server_renderer_is_not_limited():
    assert set(statuses(200, HTTP_X_SSR_TOKEN=SECRET)) == {200}


def test_anonymous_visitors_are_limited():
    assert statuses(LIMIT + 1)[-1] == 429


def test_wrong_token_is_limited_like_anyone():
    assert statuses(LIMIT + 1, HTTP_X_SSR_TOKEN="guess")[-1] == 429


def test_no_secret_configured_means_no_exemption():
    with override_settings(CORE={"SSR_SHARED_SECRET": ""}):
        assert statuses(LIMIT + 1, HTTP_X_SSR_TOKEN="")[-1] == 429


def test_secret_is_never_echoed(caplog):
    response = PublicView.as_view()(APIRequestFactory().get("/", HTTP_X_SSR_TOKEN=SECRET))
    response.render()

    assert SECRET not in response.content.decode()
    assert all(SECRET not in value for value in response.headers.values())
    assert SECRET not in caplog.text

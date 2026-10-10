from hmac import compare_digest
from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle

from core.conf import core_settings

SSR_TOKEN_HEADER = "X-SSR-Token"  # noqa: S105


def is_server_renderer(request: Request) -> bool:
    secret = core_settings().ssr_shared_secret
    token = request.headers.get(SSR_TOKEN_HEADER, "")
    return bool(secret and token) and compare_digest(token.encode(), secret.encode())


class SsrAwareAnonRateThrottle(AnonRateThrottle):
    def allow_request(self, request: Request, view: Any) -> bool:
        return is_server_renderer(request) or super().allow_request(request, view)


class SsrAwareScopedRateThrottle(ScopedRateThrottle):
    def allow_request(self, request: Request, view: Any) -> bool:
        if request.user.is_anonymous and is_server_renderer(request):
            return True
        return super().allow_request(request, view)

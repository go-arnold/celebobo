from hmac import compare_digest
from typing import Any

from rest_framework.exceptions import Throttled
from rest_framework.request import Request
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, SimpleRateThrottle

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


class FailureRateThrottle(SimpleRateThrottle):
    """Counts only failed attempts against a scope's rate (e.g. rejected coupon codes).

    Shares the cache key of ``ScopedRateThrottle`` for the same scope, so a view that throttles
    every request and one that throttles only failures draw from one budget per client.
    """

    cache_format = "throttle_%(scope)s_%(ident)s"
    # set by SimpleRateThrottle.__init__ from the scope's rate; missing from the type stubs
    num_requests: int
    duration: int

    def __init__(self, scope: str) -> None:
        self.scope = scope
        super().__init__()

    def get_cache_key(self, request: Request, view: Any = None) -> str:
        user = request.user
        ident = user.pk if user and user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def check(self, request: Request) -> None:
        self.key = self.get_cache_key(request)
        self.now = self.timer()
        self.history = [
            moment for moment in self.cache.get(self.key, []) if moment > self.now - self.duration
        ]
        if len(self.history) >= self.num_requests:
            raise Throttled(wait=self.wait())

    def record(self, request: Request) -> None:
        self.check(request)
        self.history.insert(0, self.now)
        self.cache.set(self.key, self.history, self.duration)

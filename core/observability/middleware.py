import re
from collections.abc import Callable, Coroutine
from inspect import iscoroutinefunction
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog
from django.http import HttpRequest, HttpResponseBase
from django.utils.decorators import sync_and_async_middleware

from core.conf import core_settings
from core.observability import context

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")

logger = structlog.get_logger("http")

type SyncHandler = Callable[[HttpRequest], HttpResponseBase]
type AsyncHandler = Callable[[HttpRequest], Coroutine[Any, Any, HttpResponseBase]]


@sync_and_async_middleware
def request_context_middleware(
    get_response: SyncHandler | AsyncHandler,
) -> SyncHandler | AsyncHandler:
    if iscoroutinefunction(get_response):
        async_get_response = get_response

        async def async_middleware(request: HttpRequest) -> HttpResponseBase:
            started = _start(request)
            response = await async_get_response(request)
            return _finish(request, response, started)

        return async_middleware

    sync_get_response = get_response

    def middleware(request: HttpRequest) -> HttpResponseBase:
        started = _start(request)
        response = sync_get_response(request)
        if not isinstance(response, HttpResponseBase):
            raise TypeError("Synchronous middleware chain returned a coroutine")
        return _finish(request, response, started)

    return middleware


def _start(request: HttpRequest) -> float:
    context.reset(request_id=_request_id(request), method=request.method, path=request.path)
    return perf_counter()


def _finish(request: HttpRequest, response: HttpResponseBase, started: float) -> HttpResponseBase:
    settings = core_settings()
    duration_ms = round((perf_counter() - started) * 1000, 2)
    request_id = context.current_request_id()
    if request_id:
        response[settings.request_id_header] = request_id
    response["Server-Timing"] = f"app;dur={duration_ms}"
    if not request.path.startswith(settings.quiet_paths):
        logger.info("http.request", status=response.status_code, duration_ms=duration_ms)
    return response


def _request_id(request: HttpRequest) -> str:
    candidate = request.headers.get(core_settings().request_id_header, "")
    return candidate if _REQUEST_ID.fullmatch(candidate) else uuid4().hex

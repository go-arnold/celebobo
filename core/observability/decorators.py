import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from functools import wraps
from time import perf_counter
from types import TracebackType
from typing import Any, cast

import structlog

from core.domain.errors import DomainError
from core.observability.metrics import get_metrics

USE_CASE_MARKER = "__use_case__"

logger = structlog.get_logger("use_case")


class _UseCaseRun:
    __slots__ = ("_operation", "_started")

    def __init__(self, operation: str) -> None:
        self._operation = operation
        self._started = 0.0

    def __enter__(self) -> None:
        self._started = perf_counter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        duration_ms = round((perf_counter() - self._started) * 1000, 2)
        tags = {"use_case": self._operation}
        metrics = get_metrics()
        log = logger.bind(use_case=self._operation, duration_ms=duration_ms)
        match exc:
            case None:
                log.info("use_case.completed")
                metrics.timing("use_case.duration", duration_ms, tags=tags)
            case DomainError():
                log.warning("use_case.rejected", code=exc.code)
                metrics.increment("use_case.rejected", tags={**tags, "code": exc.code})
            case GeneratorExit() | asyncio.CancelledError():
                log.info("use_case.cancelled")
                metrics.increment("use_case.cancelled", tags=tags)
            case _:
                log.error("use_case.failed", exc_info=(exc_type, exc, traceback))
                metrics.increment("use_case.failed", tags=tags)


def use_case[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    if getattr(fn, USE_CASE_MARKER, False):
        return fn
    operation = fn.__qualname__
    wrapper: Callable[..., Any]

    if inspect.isasyncgenfunction(fn):

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncIterator[Any]:
            with _UseCaseRun(operation):
                async for item in cast(Callable[P, AsyncIterator[Any]], fn)(*args, **kwargs):
                    yield item

    elif inspect.iscoroutinefunction(fn):

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            with _UseCaseRun(operation):
                return await fn(*args, **kwargs)

    else:

        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            with _UseCaseRun(operation):
                return fn(*args, **kwargs)

    setattr(wrapper, USE_CASE_MARKER, True)
    return cast(Callable[P, R], wrapper)


def logged_facade[C: type](cls: C) -> C:
    for name, member in list(vars(cls).items()):
        if not name.startswith("_") and inspect.isfunction(member):
            setattr(cls, name, use_case(member))
    return cls

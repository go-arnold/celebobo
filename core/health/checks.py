from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from uuid import uuid4

import structlog
from celery import current_app
from django.core.cache import cache
from django.db import connection

from core.registry import Registry

logger = structlog.get_logger(__name__)


class HealthCheck(Protocol):
    def run(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    healthy: bool
    duration_ms: float
    error: str | None = None


health_registry: Registry[HealthCheck] = Registry("health check")


@health_registry.register("database")
class DatabaseCheck:
    def run(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")


@health_registry.register("cache")
class CacheCheck:
    def run(self) -> None:
        key, value = f"core:health:{uuid4().hex}", uuid4().hex
        cache.set(key, value, timeout=5)
        try:
            if cache.get(key) != value:
                raise RuntimeError("cache round-trip mismatch")
        finally:
            cache.delete(key)


@health_registry.register("broker")
class BrokerCheck:
    def run(self) -> None:
        with current_app.connection_for_write() as broker:
            broker.ensure_connection(max_retries=1, timeout=2)


def run_checks(names: Iterable[str]) -> list[CheckResult]:
    return [_run(name) for name in names]


def _run(name: str) -> CheckResult:
    started = perf_counter()
    try:
        health_registry.create(name).run()
    except Exception as exc:
        logger.warning("health.check_failed", check=name, error=type(exc).__name__)
        return CheckResult(
            name, healthy=False, duration_ms=_elapsed(started), error=type(exc).__name__
        )
    return CheckResult(name, healthy=True, duration_ms=_elapsed(started))


def _elapsed(started: float) -> float:
    return round((perf_counter() - started) * 1000, 2)

from collections.abc import Mapping
from typing import Protocol

import structlog

from core.container import container
from core.registry import Registry

type Tags = Mapping[str, str]

logger = structlog.get_logger("metrics")


class Metrics(Protocol):
    def increment(self, name: str, *, value: int = 1, tags: Tags | None = None) -> None: ...

    def timing(self, name: str, milliseconds: float, *, tags: Tags | None = None) -> None: ...

    def gauge(self, name: str, value: float, *, tags: Tags | None = None) -> None: ...


metrics_registry: Registry[Metrics] = Registry("metrics backend")


@metrics_registry.register("log")
class LogMetrics:
    def increment(self, name: str, *, value: int = 1, tags: Tags | None = None) -> None:
        logger.debug("metric", kind="counter", metric=name, value=value, tags=dict(tags or {}))

    def timing(self, name: str, milliseconds: float, *, tags: Tags | None = None) -> None:
        logger.debug(
            "metric", kind="timing", metric=name, value=milliseconds, tags=dict(tags or {})
        )

    def gauge(self, name: str, value: float, *, tags: Tags | None = None) -> None:
        logger.debug("metric", kind="gauge", metric=name, value=value, tags=dict(tags or {}))


@metrics_registry.register("null")
class NullMetrics:
    def increment(self, name: str, *, value: int = 1, tags: Tags | None = None) -> None:
        return None

    def timing(self, name: str, milliseconds: float, *, tags: Tags | None = None) -> None:
        return None

    def gauge(self, name: str, value: float, *, tags: Tags | None = None) -> None:
        return None


def get_metrics() -> Metrics:
    return container.resolve(Metrics)

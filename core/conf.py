from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed


@dataclass(frozen=True, slots=True)
class CoreSettings:
    events_dispatcher: str = "celery"
    events_dedup_ttl: int = 60 * 60 * 24
    metrics_backend: str = "log"
    problem_base_uri: str = "https://api.celebobo.com/problems"
    health_checks: tuple[str, ...] = ("database", "cache")
    idempotency_cache: str = "default"
    idempotency_ttl: int = 60 * 60 * 24
    idempotency_lock_ttl: int = 30
    request_id_header: str = "X-Request-ID"
    quiet_paths: tuple[str, ...] = ("/health/",)


_TUPLE_FIELDS = frozenset({"health_checks", "quiet_paths"})


@lru_cache(maxsize=1)
def core_settings() -> CoreSettings:
    raw = {key.lower(): value for key, value in getattr(settings, "CORE", {}).items()}
    if unknown := raw.keys() - {field.name for field in fields(CoreSettings)}:
        raise ImproperlyConfigured(f"Unknown CORE settings: {', '.join(sorted(unknown))}")
    values: dict[str, Any] = {
        key: tuple(value) if key in _TUPLE_FIELDS else value for key, value in raw.items()
    }
    return CoreSettings(**values)


def _reset_core_settings(*, setting: str, **_: Any) -> None:
    if setting == "CORE":
        core_settings.cache_clear()


setting_changed.connect(_reset_core_settings)

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

_sections: dict[str, Any] = {}


def load_section[S: "DataclassInstance"](name: str, schema: type[S]) -> S:
    if name not in _sections:
        raw = {key.lower(): value for key, value in getattr(settings, name, {}).items()}
        if unknown := raw.keys() - {item.name for item in fields(schema)}:
            raise ImproperlyConfigured(f"Unknown {name} settings: {', '.join(sorted(unknown))}")
        values = {
            key: tuple(value) if isinstance(value, list) else value for key, value in raw.items()
        }
        _sections[name] = schema(**values)
    section: S = _sections[name]
    return section


def _reset_section(*, setting: str, **_: Any) -> None:
    _sections.pop(setting, None)


setting_changed.connect(_reset_section)


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


def core_settings() -> CoreSettings:
    return load_section("CORE", CoreSettings)

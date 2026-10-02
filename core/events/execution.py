from collections.abc import Callable, Mapping
from typing import Any

import structlog
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from core.conf import core_settings
from core.events.base import DomainEvent
from core.events.codec import decode

logger = structlog.get_logger(__name__)


def handler_path(handler: Callable[..., object]) -> str:
    qualname = handler.__qualname__
    if "<" in qualname:
        raise ImproperlyConfigured(f"Background handler {qualname} must be a module-level function")
    return f"{handler.__module__}.{qualname}"


def run_background_handler(path: str, event_name: str, payload: Mapping[str, Any]) -> None:
    event_type = import_string(event_name)
    if not (isinstance(event_type, type) and issubclass(event_type, DomainEvent)):
        raise TypeError(f"{event_name} is not a DomainEvent")
    event = decode(event_type, payload)
    marker = f"core:events:done:{event.event_id}:{path}"
    if cache.get(marker):
        logger.info("event.handler_skipped", handler=path, event_type=event_name)
        return
    with structlog.contextvars.bound_contextvars(
        event_type=event_name, event_id=str(event.event_id), handler=path
    ):
        import_string(path)(event)
    cache.set(marker, 1, timeout=core_settings().events_dedup_ttl)

from collections import defaultdict
from collections.abc import Callable, Iterator
from functools import partial
from typing import Any

import structlog
from django.db import transaction

from core.events.base import DomainEvent
from core.events.contracts import Dispatcher
from core.events.dispatchers import configured_dispatcher
from core.events.execution import handler_path

type Handler = Callable[[Any], object]

logger = structlog.get_logger(__name__)


class EventBus:
    def __init__(self, dispatcher: Callable[[], Dispatcher]) -> None:
        self._dispatcher = dispatcher
        self._inline: defaultdict[type[DomainEvent], list[Handler]] = defaultdict(list)
        self._background: defaultdict[type[DomainEvent], list[str]] = defaultdict(list)

    def on[H: Handler](
        self, *event_types: type[DomainEvent], background: bool = False
    ) -> Callable[[H], H]:
        if not event_types:
            raise ValueError("Subscribe to at least one event type")

        def decorator(handler: H) -> H:
            self.subscribe(handler, *event_types, background=background)
            return handler

        return decorator

    def subscribe(
        self, handler: Handler, *event_types: type[DomainEvent], background: bool = False
    ) -> None:
        for event_type in event_types:
            if background:
                path = handler_path(handler)
                if path not in self._background[event_type]:
                    self._background[event_type].append(path)
            elif handler not in self._inline[event_type]:
                self._inline[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        transaction.on_commit(partial(self.dispatch, event))

    def dispatch(self, event: DomainEvent) -> None:
        for event_type in _lineage(type(event)):
            for handler in tuple(self._inline.get(event_type, ())):
                self._run_inline(handler, event)
            for path in tuple(self._background.get(event_type, ())):
                self._enqueue(path, event)

    def subscribers(self, event_type: type[DomainEvent]) -> tuple[str, ...]:
        inline = (_describe(handler) for handler in self._inline.get(event_type, ()))
        return (*inline, *self._background.get(event_type, ()))

    def clear(self) -> None:
        self._inline.clear()
        self._background.clear()

    def _run_inline(self, handler: Handler, event: DomainEvent) -> None:
        try:
            handler(event)
        except Exception:
            logger.exception(
                "event.handler_failed",
                event_type=event.event_name(),
                event_id=str(event.event_id),
                handler=_describe(handler),
            )

    def _enqueue(self, path: str, event: DomainEvent) -> None:
        try:
            self._dispatcher().enqueue(path, event)
        except Exception:
            logger.exception(
                "event.enqueue_failed",
                event_type=event.event_name(),
                event_id=str(event.event_id),
                handler=path,
            )


def _describe(handler: Handler) -> str:
    return f"{handler.__module__}.{getattr(handler, '__qualname__', repr(handler))}"


def _lineage(event_type: type[DomainEvent]) -> Iterator[type[DomainEvent]]:
    return (cls for cls in event_type.__mro__ if issubclass(cls, DomainEvent))


event_bus = EventBus(dispatcher=configured_dispatcher)

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
        self._transactional: defaultdict[type[DomainEvent], list[Handler]] = defaultdict(list)
        self._background: defaultdict[type[DomainEvent], list[str]] = defaultdict(list)

    def on[H: Handler](
        self,
        *event_types: type[DomainEvent],
        background: bool = False,
        transactional: bool = False,
    ) -> Callable[[H], H]:
        if not event_types:
            raise ValueError("Subscribe to at least one event type")

        def decorator(handler: H) -> H:
            self.subscribe(
                handler, *event_types, background=background, transactional=transactional
            )
            return handler

        return decorator

    # transactional: the handler runs at publish time, inside the publisher's transaction; if it
    # fails, the error reaches the publisher and the whole change rolls back (money records)
    def subscribe(
        self,
        handler: Handler,
        *event_types: type[DomainEvent],
        background: bool = False,
        transactional: bool = False,
    ) -> None:
        if background and transactional:
            raise ValueError("A handler is either background or transactional")
        for event_type in event_types:
            if transactional:
                if handler not in self._transactional[event_type]:
                    self._transactional[event_type].append(handler)
            elif background:
                path = handler_path(handler)
                if path not in self._background[event_type]:
                    self._background[event_type].append(path)
            elif handler not in self._inline[event_type]:
                self._inline[event_type].append(handler)

    def publish(self, event: DomainEvent) -> None:
        handlers = [
            handler
            for event_type in _lineage(type(event))
            for handler in self._transactional.get(event_type, ())
        ]
        if handlers:
            with transaction.atomic():
                for handler in handlers:
                    handler(event)
        transaction.on_commit(partial(self.dispatch, event))

    def dispatch(self, event: DomainEvent) -> None:
        for event_type in _lineage(type(event)):
            for handler in tuple(self._inline.get(event_type, ())):
                self._run_inline(handler, event)
            for path in tuple(self._background.get(event_type, ())):
                self._enqueue(path, event)

    def subscribers(self, event_type: type[DomainEvent]) -> tuple[str, ...]:
        transactional = (_describe(handler) for handler in self._transactional.get(event_type, ()))
        inline = (_describe(handler) for handler in self._inline.get(event_type, ()))
        return (*transactional, *inline, *self._background.get(event_type, ()))

    def clear(self) -> None:
        self._transactional.clear()
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

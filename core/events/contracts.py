from typing import Protocol

from core.events.base import DomainEvent


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...


class Dispatcher(Protocol):
    def enqueue(self, handler_path: str, event: DomainEvent) -> None: ...

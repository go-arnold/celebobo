from core.conf import core_settings
from core.events.base import DomainEvent
from core.events.codec import encode
from core.events.contracts import Dispatcher
from core.events.execution import run_background_handler
from core.registry import Registry

dispatcher_registry: Registry[Dispatcher] = Registry("event dispatcher")


@dispatcher_registry.register("inline")
class InlineDispatcher:
    def enqueue(self, handler_path: str, event: DomainEvent) -> None:
        run_background_handler(handler_path, event.event_name(), encode(event))


@dispatcher_registry.register("celery")
class CeleryDispatcher:
    def enqueue(self, handler_path: str, event: DomainEvent) -> None:
        from core.events.tasks import dispatch_event

        dispatch_event.delay(handler_path, event.event_name(), encode(event))


def configured_dispatcher() -> Dispatcher:
    return dispatcher_registry.create(core_settings().events_dispatcher)

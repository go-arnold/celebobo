from importlib import import_module

from django.utils.module_loading import autodiscover_modules

from core.api.idempotency import IdempotencyStore
from core.conf import core_settings
from core.container import Container, container
from core.events.bus import event_bus
from core.events.contracts import EventPublisher
from core.observability.metrics import Metrics, metrics_registry

APP_MODULES = ("permissions", "handlers")
CORE_PROVIDERS = ("core.events.tasks", "core.health.checks", "core.mail")


def bootstrap(target: Container = container) -> None:
    for module in CORE_PROVIDERS:
        import_module(module)
    register_defaults(target)
    autodiscover_modules(*APP_MODULES)


def register_defaults(target: Container) -> None:
    target.register(EventPublisher, lambda _: event_bus, replace=True)
    target.register(
        Metrics, lambda _: metrics_registry.create(core_settings().metrics_backend), replace=True
    )
    target.register(IdempotencyStore, lambda _: IdempotencyStore.from_settings(), replace=True)

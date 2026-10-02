from django.utils import timezone

from apps.push.adapters.webpush import WebPushSender
from apps.push.conf import push_settings
from apps.push.facades import PushFacade
from apps.push.repositories import SubscriptionRepository
from apps.push.selectors import DeviceSelector
from apps.push.services.contracts import PushSender
from apps.push.services.devices import DeviceService, PushDispatcher
from core.container import Container, Lifetime


def register(container: Container) -> None:
    container.register(PushSender, lambda _: WebPushSender(push_settings()))
    container.register(PushFacade, _push_facade, lifetime=Lifetime.TRANSIENT)


def _push_facade(container: Container) -> PushFacade:
    settings = push_settings()
    subscriptions = SubscriptionRepository()
    return PushFacade(
        devices=DeviceService(subscriptions, max_devices=settings.max_devices),
        dispatcher=PushDispatcher(
            subscriptions,
            container.resolve(PushSender),
            max_failures=settings.max_failures,
            clock=timezone.now,
        ),
        selector=DeviceSelector(),
        public_key=settings.vapid_public_key,
        enabled=settings.enabled,
    )

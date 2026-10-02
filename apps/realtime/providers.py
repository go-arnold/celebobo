from apps.accounts.selectors import DirectorySelector
from apps.messaging.selectors import ConversationSelector, NotificationSelector
from apps.realtime.adapters.channels import CachePresenceStore, ChannelLayerBroadcaster
from apps.realtime.conf import realtime_settings
from apps.realtime.services.contracts import Broadcaster, PresenceStore
from apps.realtime.services.presence import PresenceService
from apps.realtime.services.relay import RealtimeRelay
from core.container import Container, Lifetime


def register(container: Container) -> None:
    container.register(Broadcaster, lambda _: ChannelLayerBroadcaster())
    container.register(PresenceStore, lambda _: CachePresenceStore())
    container.register(PresenceService, _presence, lifetime=Lifetime.TRANSIENT)
    container.register(RealtimeRelay, _relay, lifetime=Lifetime.TRANSIENT)


def _presence(container: Container) -> PresenceService:
    return PresenceService(container.resolve(PresenceStore), ttl=realtime_settings().presence_ttl)


def _relay(container: Container) -> RealtimeRelay:
    return RealtimeRelay(
        container.resolve(Broadcaster),
        conversations=ConversationSelector(),
        notifications=NotificationSelector(),
        directory=DirectorySelector(),
    )

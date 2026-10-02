from django.utils import timezone

from apps.messaging.adapters import notifiers
from apps.messaging.adapters.gateways import AccountsDirectory, MessagingOrderThreads, OrdersGateway
from apps.messaging.conf import messaging_settings
from apps.messaging.facades import (
    ConversationFacade,
    NotificationFacade,
    NotificationRouter,
    ProposalFacade,
)
from apps.messaging.repositories import (
    ConversationRepository,
    MessageRepository,
    NotificationRepository,
    ParticipantRepository,
    ProposalRepository,
)
from apps.messaging.selectors import ConversationSelector, NotificationSelector
from apps.messaging.services.contracts import Directory, OrderGateway
from apps.messaging.services.conversations import ConversationService
from apps.messaging.services.notifications import (
    InboxService,
    NotificationFanout,
    NotificationService,
    notifier_registry,
)
from apps.messaging.services.proposals import ProposalService
from apps.orders.services.contracts import OrderThreads
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher

ADAPTER_MODULES = (notifiers,)


def register(container: Container) -> None:
    container.register(Directory, lambda _: AccountsDirectory())
    container.register(OrderGateway, lambda _: OrdersGateway())
    container.register(OrderThreads, lambda _: MessagingOrderThreads(), replace=True)
    container.register(ConversationService, _conversations, lifetime=Lifetime.TRANSIENT)
    container.register(NotificationService, _notifications, lifetime=Lifetime.TRANSIENT)
    container.register(ConversationFacade, _conversation_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ProposalFacade, _proposal_facade, lifetime=Lifetime.TRANSIENT)
    container.register(NotificationFacade, _notification_facade, lifetime=Lifetime.TRANSIENT)
    container.register(NotificationRouter, _router, lifetime=Lifetime.TRANSIENT)


def _conversations(_: Container) -> ConversationService:
    return ConversationService(
        ConversationRepository(),
        MessageRepository(),
        ParticipantRepository(),
        NotificationRepository(),
        clock=timezone.now,
    )


def _notifications(_: Container) -> NotificationService:
    return NotificationService(
        [notifier_registry.create(name) for name in messaging_settings().notification_channels]
    )


def _conversation_facade(container: Container) -> ConversationFacade:
    return ConversationFacade(
        conversations=container.resolve(ConversationService),
        selector=ConversationSelector(),
        directory=container.resolve(Directory),
        publisher=container.resolve(EventPublisher),
    )


def _proposal_facade(container: Container) -> ProposalFacade:
    return ProposalFacade(
        proposals=ProposalService(
            ProposalRepository(),
            MessageRepository(),
            container.resolve(ConversationService),
            container.resolve(OrderGateway),
            clock=timezone.now,
        ),
        repository=ProposalRepository(),
        selector=ConversationSelector(),
        publisher=container.resolve(EventPublisher),
    )


def _notification_facade(_: Container) -> NotificationFacade:
    return NotificationFacade(
        inbox=InboxService(NotificationRepository(), clock=timezone.now),
        selector=NotificationSelector(),
    )


def _router(container: Container) -> NotificationRouter:
    return NotificationRouter(
        fanout=NotificationFanout(
            container.resolve(NotificationService),
            NotificationRepository(),
            container.resolve(OrderGateway),
            container.resolve(Directory),
        ),
        selector=ConversationSelector(),
        directory=container.resolve(Directory),
    )

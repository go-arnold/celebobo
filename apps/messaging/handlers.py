from django.db import transaction

from apps.messaging.domain.events import (
    ConversationAssigned,
    ConversationOpened,
    MessagePosted,
    PriceProposalAnswered,
    PriceProposed,
)
from apps.messaging.facades import NotificationRouter
from apps.messaging.services.contracts import Directory
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.events import (
    AssignmentDeclined,
    OrderAssigned,
    OrderPlaced,
    OrderStatusChanged,
)
from core.container import container
from core.events.bus import event_bus


@event_bus.on(OrderAssigned)
def bring_reseller_into_order_thread(event: OrderAssigned) -> None:
    name = container.resolve(Directory).reseller_name(event.reseller_id) or "Le revendeur"
    with transaction.atomic():
        container.resolve(ConversationService).sync_order_reseller(
            event.order_id, event.reseller_id, name
        )


@event_bus.on(AssignmentDeclined)
def remove_reseller_from_order_thread(event: AssignmentDeclined) -> None:
    with transaction.atomic():
        container.resolve(ConversationService).sync_order_reseller(event.order_id, None, "")


@event_bus.on(OrderStatusChanged)
def close_thread_of_finished_order(event: OrderStatusChanged) -> None:
    if event.status.is_final:
        with transaction.atomic():
            container.resolve(ConversationService).close_for_order(
                event.order_id, event.status.label
            )


@event_bus.on(OrderPlaced, background=True)
def notify_order_placed(event: OrderPlaced) -> None:
    container.resolve(NotificationRouter).order_placed(event)


@event_bus.on(OrderAssigned, background=True)
def notify_order_assigned(event: OrderAssigned) -> None:
    container.resolve(NotificationRouter).order_assigned(event)


@event_bus.on(AssignmentDeclined, background=True)
def notify_assignment_declined(event: AssignmentDeclined) -> None:
    container.resolve(NotificationRouter).assignment_declined(event)


@event_bus.on(OrderStatusChanged, background=True)
def notify_order_status(event: OrderStatusChanged) -> None:
    container.resolve(NotificationRouter).order_status_changed(event)


@event_bus.on(MessagePosted, background=True)
def notify_message_posted(event: MessagePosted) -> None:
    container.resolve(NotificationRouter).message_posted(event)


@event_bus.on(ConversationOpened, background=True)
def notify_support_opened(event: ConversationOpened) -> None:
    container.resolve(NotificationRouter).support_opened(event)


@event_bus.on(ConversationAssigned, background=True)
def notify_conversation_assigned(event: ConversationAssigned) -> None:
    container.resolve(NotificationRouter).conversation_assigned(event)


@event_bus.on(PriceProposed, background=True)
def notify_price_proposed(event: PriceProposed) -> None:
    container.resolve(NotificationRouter).price_proposed(event)


@event_bus.on(PriceProposalAnswered, background=True)
def notify_price_answered(event: PriceProposalAnswered) -> None:
    container.resolve(NotificationRouter).price_answered(event)

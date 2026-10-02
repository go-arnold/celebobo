from apps.accounts.domain.events import AvailabilityChanged
from apps.catalog.domain.events import StockLow
from apps.messaging.domain.events import (
    ConversationAssigned,
    ConversationClosed,
    ConversationRead,
    ConversationReopened,
    MessagePosted,
    NotificationCreated,
)
from apps.orders.domain.events import (
    OrderAssigned,
    OrderPlaced,
    OrderRepriced,
    OrderStatusChanged,
)
from apps.realtime.domain.protocol import ServerEvent
from apps.realtime.services.relay import RealtimeRelay
from apps.resellers.domain.events import ApplicationSubmitted
from apps.sales.domain.events import (
    CommissionChanged,
    PayoutRecorded,
    SaleDeleted,
    SaleRecorded,
    SaleRefunded,
    SaleUpdated,
)
from core.container import container
from core.events.bus import event_bus


def _relay() -> RealtimeRelay:
    return container.resolve(RealtimeRelay)


@event_bus.on(MessagePosted)
def push_message(event: MessagePosted) -> None:
    _relay().message_posted(event.conversation_id, event.message_id)


@event_bus.on(ConversationRead)
def push_read_receipt(event: ConversationRead) -> None:
    _relay().conversation_read(event.conversation_id, event.user_id, event.message_id)


@event_bus.on(ConversationClosed)
def push_conversation_closed(event: ConversationClosed) -> None:
    _relay().conversation_lifecycle(ServerEvent.CONVERSATION_CLOSED, event.conversation_id)


@event_bus.on(ConversationReopened)
def push_conversation_reopened(event: ConversationReopened) -> None:
    _relay().conversation_lifecycle(ServerEvent.CONVERSATION_REOPENED, event.conversation_id)


@event_bus.on(ConversationAssigned)
def push_conversation_assigned(event: ConversationAssigned) -> None:
    _relay().conversation_lifecycle(
        ServerEvent.CONVERSATION_ASSIGNED, event.conversation_id, reseller_id=event.reseller_id
    )


@event_bus.on(NotificationCreated)
def push_notification(event: NotificationCreated) -> None:
    _relay().notification_created(event.notification_id, event.recipient_id)


@event_bus.on(OrderPlaced)
def push_order_created(event: OrderPlaced) -> None:
    _relay().order_event(ServerEvent.ORDER_CREATED, event.order_id)


@event_bus.on(OrderAssigned)
def push_order_assigned(event: OrderAssigned) -> None:
    _relay().order_event(
        ServerEvent.ORDER_ASSIGNED,
        event.order_id,
        reseller_id=event.reseller_id,
        previous_reseller_id=event.previous_reseller_id,
    )


@event_bus.on(OrderStatusChanged)
def push_order_status(event: OrderStatusChanged) -> None:
    _relay().order_event(
        ServerEvent.ORDER_STATUS_CHANGED,
        event.order_id,
        previous_status=event.previous_status.value,
    )


@event_bus.on(OrderRepriced)
def push_order_repriced(event: OrderRepriced) -> None:
    _relay().order_event(ServerEvent.ORDER_UPDATED, event.order_id, item_id=event.item_id)


@event_bus.on(AvailabilityChanged)
def push_availability(event: AvailabilityChanged) -> None:
    _relay().presence_changed(event.user_id, online=True, availability=event.availability.value)


@event_bus.on(StockLow)
def push_low_stock(event: StockLow) -> None:
    _relay().stock_low(event.product_id, event.variant_id, event.stock, event.threshold)


@event_bus.on(SaleRecorded)
def push_sale_created(event: SaleRecorded) -> None:
    _relay().sale_event(ServerEvent.SALE_CREATED, event.sale_id, event.seller_id, total=event.total)


@event_bus.on(SaleUpdated, SaleRefunded)
def push_sale_updated(event: SaleUpdated | SaleRefunded) -> None:
    _relay().sale_event(ServerEvent.SALE_UPDATED, event.sale_id, event.seller_id)


@event_bus.on(SaleDeleted)
def push_sale_deleted(event: SaleDeleted) -> None:
    _relay().sale_event(ServerEvent.SALE_DELETED, event.sale_id, event.seller_id)


@event_bus.on(CommissionChanged)
def push_commission(event: CommissionChanged) -> None:
    _relay().reseller_event(ServerEvent.COMMISSION_UPDATED, event.reseller_id, delta=event.delta)


@event_bus.on(PayoutRecorded)
def push_payout(event: PayoutRecorded) -> None:
    _relay().reseller_event(
        ServerEvent.PAYOUT_CREATED,
        event.reseller_id,
        payout_id=event.payout_id,
        amount=event.amount,
    )


@event_bus.on(ApplicationSubmitted)
def push_reseller_application(event: ApplicationSubmitted) -> None:
    _relay().staff_event(
        ServerEvent.RESELLER_APPLICATION_CREATED, application_id=event.application_id
    )

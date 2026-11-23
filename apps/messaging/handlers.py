from django.db import transaction

from apps.cagnotte.domain.events import CashbackPaid
from apps.cash.domain.events import CashOverdue
from apps.messaging.domain.events import (
    ConversationAssigned,
    ConversationOpened,
    MessagePosted,
    PriceProposalAnswered,
    PriceProposed,
    ShippingQuoteAnswered,
    ShippingQuoted,
)
from apps.messaging.facades import NotificationRouter
from apps.messaging.services.contracts import Directory
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.events import (
    AssignmentDeclined,
    DeliveryAttemptFailed,
    DeliveryCodeIssued,
    DeliveryCodeLocked,
    OrderAssigned,
    OrderPlaced,
    OrderRefunded,
    OrderStatusChanged,
    RefundDue,
    ResellerRated,
)
from apps.sales.domain.events import PayoutRecorded, PayoutStatementPrepared
from apps.standing.domain.events import LevelChanged, SanctionUpdated
from apps.warranty.domain.events import ClaimSubmitted, ClaimUpdated
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
def wind_down_thread_of_finished_order(event: OrderStatusChanged) -> None:
    if event.status.is_final:
        with transaction.atomic():
            container.resolve(ConversationService).wind_down_for_order(
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


@event_bus.on(DeliveryCodeIssued, background=True)
def notify_delivery_code(event: DeliveryCodeIssued) -> None:
    container.resolve(NotificationRouter).delivery_code_issued(event)


@event_bus.on(DeliveryAttemptFailed, background=True)
def notify_delivery_attempt(event: DeliveryAttemptFailed) -> None:
    container.resolve(NotificationRouter).delivery_attempt(event)


@event_bus.on(ResellerRated, background=True)
def notify_reseller_rated(event: ResellerRated) -> None:
    container.resolve(NotificationRouter).reseller_rated(event)


@event_bus.on(PayoutStatementPrepared, background=True)
def notify_payout_statement(event: PayoutStatementPrepared) -> None:
    container.resolve(NotificationRouter).payout_statement_prepared(event)


@event_bus.on(PayoutRecorded, background=True)
def notify_payout_paid(event: PayoutRecorded) -> None:
    container.resolve(NotificationRouter).payout_recorded(event)


@event_bus.on(LevelChanged, background=True)
def notify_level_changed(event: LevelChanged) -> None:
    container.resolve(NotificationRouter).level_changed(event)


@event_bus.on(SanctionUpdated, background=True)
def notify_sanction(event: SanctionUpdated) -> None:
    container.resolve(NotificationRouter).sanction_updated(event)


@event_bus.on(CashbackPaid, background=True)
def notify_cashback_paid(event: CashbackPaid) -> None:
    container.resolve(NotificationRouter).cashback_paid(event)


@event_bus.on(CashOverdue, background=True)
def notify_cash_overdue(event: CashOverdue) -> None:
    container.resolve(NotificationRouter).cash_overdue(event)


@event_bus.on(ClaimSubmitted, background=True)
def notify_claim_submitted(event: ClaimSubmitted) -> None:
    container.resolve(NotificationRouter).claim_submitted(event)


@event_bus.on(ClaimUpdated, background=True)
def notify_claim_updated(event: ClaimUpdated) -> None:
    container.resolve(NotificationRouter).claim_updated(event)


@event_bus.on(DeliveryCodeLocked, background=True)
def notify_delivery_code_locked(event: DeliveryCodeLocked) -> None:
    container.resolve(NotificationRouter).delivery_code_locked(event)


@event_bus.on(RefundDue, background=True)
def notify_refund_due(event: RefundDue) -> None:
    container.resolve(NotificationRouter).refund_due(event)


@event_bus.on(OrderRefunded, background=True)
def notify_order_refunded(event: OrderRefunded) -> None:
    container.resolve(NotificationRouter).order_refunded(event)


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


@event_bus.on(ShippingQuoted, background=True)
def notify_shipping_quoted(event: ShippingQuoted) -> None:
    container.resolve(NotificationRouter).shipping_quoted(event)


@event_bus.on(ShippingQuoteAnswered, background=True)
def notify_shipping_answered(event: ShippingQuoteAnswered) -> None:
    container.resolve(NotificationRouter).shipping_answered(event)

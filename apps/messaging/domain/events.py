from decimal import Decimal

from apps.messaging.domain.enums import ConversationKind
from core.events.base import DomainEvent, domain_event


@domain_event
class ConversationOpened(DomainEvent):
    conversation_id: int
    kind: ConversationKind
    client_id: int


@domain_event
class ConversationAssigned(DomainEvent):
    conversation_id: int
    reseller_id: int


@domain_event
class ConversationClosed(DomainEvent):
    conversation_id: int


@domain_event
class ConversationReopened(DomainEvent):
    conversation_id: int


@domain_event
class MessagePosted(DomainEvent):
    conversation_id: int
    message_id: int
    sender_id: int | None


@domain_event
class ConversationRead(DomainEvent):
    conversation_id: int
    user_id: int
    message_id: int


@domain_event
class PriceProposed(DomainEvent):
    conversation_id: int
    proposal_id: int
    order_id: int | None
    item_id: int
    previous_price: Decimal
    price: Decimal


@domain_event
class PriceProposalAnswered(DomainEvent):
    conversation_id: int
    proposal_id: int
    accepted: bool


@domain_event
class NotificationCreated(DomainEvent):
    notification_id: int
    recipient_id: int

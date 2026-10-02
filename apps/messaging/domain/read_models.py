from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apps.messaging.domain.enums import (
    ConversationKind,
    ConversationStatus,
    MessageKind,
    NotificationKind,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ParticipantView:
    id: int
    name: str
    role: str
    avatar: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageView:
    id: int
    conversation_id: int
    kind: MessageKind
    body: str
    attachment: str
    metadata: dict[str, Any]
    sender: ParticipantView | None
    client_msg_id: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationView:
    id: int
    kind: ConversationKind
    status: ConversationStatus
    subject: str
    order_id: int | None
    order_number: str | None
    client: ParticipantView
    reseller: ParticipantView | None
    last_message: MessageView | None
    unread_count: int
    created_at: datetime
    last_message_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MessagePage:
    messages: list[MessageView]
    next_before: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationView:
    id: int
    kind: NotificationKind
    title: str
    body: str
    link: str
    is_read: bool
    conversation_id: int | None
    order_id: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class UnreadCounts:
    notifications: int
    conversations: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Audience:
    conversation_id: int
    kind: ConversationKind
    client_id: int
    client_name: str
    reseller_id: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposalContext:
    conversation_id: int
    client_id: int
    proposer_id: int | None
    product: str
    previous_price: str
    proposed_price: str
    reason: str

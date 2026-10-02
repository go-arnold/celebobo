from dataclasses import dataclass
from decimal import Decimal

from apps.messaging.domain.enums import ConversationKind, ConversationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class PostMessage:
    body: str = ""
    attachment: str = ""
    client_msg_id: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenSupport:
    message: str
    subject: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ProposePrice:
    item_id: int
    new_price: Decimal
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversationFilters:
    kind: ConversationKind | None = None
    status: ConversationStatus | None = None
    unread: bool = False
    search: str | None = None

from enum import StrEnum


class ConversationKind(StrEnum):
    ORDER = "order"
    SUPPORT = "support"


class ConversationStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class MessageKind(StrEnum):
    TEXT = "text"
    SYSTEM = "system"
    PRICE_PROPOSAL = "price_proposal"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    SUPERSEDED = "superseded"


class NotificationKind(StrEnum):
    ORDER_PLACED = "order_placed"
    ORDER_ASSIGNED = "order_assigned"
    ASSIGNMENT_DECLINED = "assignment_declined"
    ORDER_STATUS = "order_status"
    NEW_MESSAGE = "new_message"
    SUPPORT_REQUEST = "support_request"
    CONVERSATION_ASSIGNED = "conversation_assigned"
    PRICE_PROPOSED = "price_proposed"
    PRICE_ANSWERED = "price_answered"

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.domain.errors import ValidationFailed

MAX_REF_LENGTH = 64


class ClientMessage(StrEnum):
    SUBSCRIBE = "conversation.subscribe"
    UNSUBSCRIBE = "conversation.unsubscribe"
    SEND = "message.send"
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    READ = "message.read"
    PING = "presence.ping"


class ServerEvent(StrEnum):
    READY = "session.ready"
    SUBSCRIBED = "conversation.subscribed"
    UNSUBSCRIBED = "conversation.unsubscribed"
    ACK = "message.ack"
    PONG = "presence.pong"
    ERROR = "error"
    MESSAGE_CREATED = "message.created"
    TYPING = "conversation.typing"
    READ = "conversation.read"
    CONVERSATION_UPDATED = "conversation.updated"
    CONVERSATION_CLOSED = "conversation.closed"
    CONVERSATION_REOPENED = "conversation.reopened"
    CONVERSATION_ASSIGNED = "conversation.assigned"
    NOTIFICATION_CREATED = "notification.created"
    UNREAD_COUNTS = "unread.counts"
    ORDER_CREATED = "order.created"
    ORDER_ASSIGNED = "order.assigned"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_UPDATED = "order.updated"
    PRESENCE_CHANGED = "presence.changed"
    STOCK_LOW = "stock.low"
    SALE_CREATED = "sale.created"
    SALE_UPDATED = "sale.updated"
    SALE_DELETED = "sale.deleted"
    COMMISSION_UPDATED = "commission.updated"
    PAYOUT_CREATED = "payout.created"
    RESELLER_APPLICATION_CREATED = "reseller_application.created"


class InvalidEnvelope(ValidationFailed):
    default_code = "invalid_envelope"
    default_detail = "Message WebSocket invalide."


@dataclass(frozen=True, slots=True)
class Envelope:
    type: ClientMessage
    data: Mapping[str, Any] = field(default_factory=dict)
    ref: str | None = None

    @classmethod
    def parse(cls, raw: object) -> "Envelope":
        if not isinstance(raw, Mapping):
            raise InvalidEnvelope
        try:
            kind = ClientMessage(str(raw.get("type")))
        except ValueError as exc:
            raise InvalidEnvelope(f"Type inconnu : {raw.get('type')!r}.") from exc
        data = raw.get("data", {})
        ref = raw.get("ref")
        if not isinstance(data, Mapping) or (
            ref is not None and (not isinstance(ref, str) or len(ref) > MAX_REF_LENGTH)
        ):
            raise InvalidEnvelope
        return cls(type=kind, data=data, ref=ref)

    def integer(self, key: str) -> int:
        value = self.data.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InvalidEnvelope(f"Champ « {key} » invalide.")
        return value

    def text(self, key: str, *, limit: int) -> str:
        value = self.data.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            raise InvalidEnvelope(f"Champ « {key} » invalide.")
        return value


def outbound(
    event: ServerEvent, data: Mapping[str, Any], *, ref: str | None = None
) -> dict[str, Any]:
    message: dict[str, Any] = {"type": event.value, "data": dict(data)}
    if ref is not None:
        message["ref"] = ref
    return message

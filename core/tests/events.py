from datetime import date
from decimal import Decimal
from enum import StrEnum

from core.events.base import DomainEvent, domain_event


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"


@domain_event
class OrderPlaced(DomainEvent):
    order_id: int
    total: Decimal
    channel: Channel
    delivery_date: date | None = None
    item_ids: tuple[int, ...] = ()
    labels: dict[str, str] | None = None


@domain_event
class PriorityOrderPlaced(OrderPlaced):
    priority: int = 1


received: list[DomainEvent] = []


def record_in_background(event: DomainEvent) -> None:
    received.append(event)

from decimal import Decimal

from apps.orders.domain.enums import OrderStatus
from core.events.base import DomainEvent, domain_event


@domain_event
class OrderPlaced(DomainEvent):
    order_id: int
    number: str
    client_id: int
    total: Decimal


@domain_event
class OrderAssigned(DomainEvent):
    order_id: int
    reseller_id: int
    previous_reseller_id: int | None = None


@domain_event
class AssignmentDeclined(DomainEvent):
    order_id: int
    reseller_id: int
    reason: str = ""


@domain_event
class OrderStatusChanged(DomainEvent):
    order_id: int
    client_id: int
    reseller_id: int | None
    previous_status: OrderStatus
    status: OrderStatus


@domain_event
class OrderRepriced(DomainEvent):
    order_id: int
    item_id: int
    previous_price: Decimal
    price: Decimal
    total: Decimal

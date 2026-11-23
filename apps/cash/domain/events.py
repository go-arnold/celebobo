from decimal import Decimal

from core.events.base import DomainEvent, domain_event


@domain_event
class CashOverdue(DomainEvent):
    reseller_id: int
    order_number: str
    amount: Decimal


@domain_event
class CashRemitted(DomainEvent):
    reseller_id: int
    amount: Decimal

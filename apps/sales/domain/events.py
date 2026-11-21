from datetime import date
from decimal import Decimal

from apps.sales.domain.enums import RefundKind
from core.events.base import DomainEvent, domain_event


@domain_event
class SaleRecorded(DomainEvent):
    sale_id: int
    seller_id: int
    product_id: int
    total: Decimal


@domain_event
class SaleUpdated(DomainEvent):
    sale_id: int
    seller_id: int


@domain_event
class SaleRefunded(DomainEvent):
    sale_id: int
    seller_id: int
    kind: RefundKind
    amount: Decimal


@domain_event
class SaleDeleted(DomainEvent):
    sale_id: int
    seller_id: int


@domain_event
class OrderConverted(DomainEvent):
    order_id: int
    sale_ids: tuple[int, ...]


@domain_event
class CommissionChanged(DomainEvent):
    reseller_id: int
    delta: Decimal


@domain_event
class PayoutRecorded(DomainEvent):
    payout_id: int
    reseller_id: int
    amount: Decimal
    statement_id: int | None = None
    payout_date: date | None = None


@domain_event
class PayoutStatementPrepared(DomainEvent):
    statement_id: int
    reseller_id: int
    total: Decimal
    payout_date: date

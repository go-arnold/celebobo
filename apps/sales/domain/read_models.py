from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.enums import CommissionKind, RefundKind, SaleStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonRef:
    id: int
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundView:
    id: int
    kind: RefundKind
    amount: Decimal
    reason: str
    by: PersonRef | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SaleView:
    id: int
    product_id: int
    variant_id: int | None
    product_name: str
    variant_label: str
    product_image: str
    quantity: int
    unit_price: Decimal
    unit_cost: Decimal | None
    total: Decimal
    refunded_amount: Decimal
    profit: Decimal | None
    payment_method: PaymentMethod
    status: SaleStatus
    sold_to: str
    buyer: PersonRef | None
    seller: PersonRef
    order_id: int | None
    order_number: str | None
    sold_at: datetime
    recorded_at: datetime
    refunds: tuple[RefundView, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SalesStats:
    revenue: Decimal
    profit: Decimal
    count: int
    units: int
    average: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ConvertibleOrderView:
    id: int
    number: str
    status: str
    client_name: str
    total: Decimal
    created_at: datetime
    convertible: bool
    blocked_reason: str | None
    items_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CommissionEntryView:
    id: int
    kind: CommissionKind
    sale_id: int | None
    rate: Decimal
    base_amount: Decimal
    amount: Decimal
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CommissionSummary:
    reseller: PersonRef
    rate: Decimal
    earned_this_month: Decimal
    earned_total: Decimal
    paid_total: Decimal
    due: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthlyCommission:
    month: str
    earned: Decimal
    paid: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class PayoutView:
    id: int
    reseller: PersonRef
    amount: Decimal
    note: str
    paid_at: datetime
    paid_by: PersonRef | None

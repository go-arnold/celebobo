from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.enums import RefundKind, SalesPeriod, SaleStatus
from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordSale:
    product_id: int
    quantity: int
    unit_price: Decimal
    payment_method: PaymentMethod
    variant_id: int | None = None
    sold_at: datetime | None = None
    sold_to: str = ""
    buyer_id: int | None = None
    seller_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class EditSale:
    unit_price: Maybe[Decimal] = UNSET
    payment_method: Maybe[PaymentMethod] = UNSET
    sold_at: Maybe[datetime] = UNSET
    sold_to: Maybe[str] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class RefundSale:
    kind: RefundKind
    amount: Decimal | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ConversionLine:
    item_id: int
    unit_price: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ConvertOrder:
    payment_method: PaymentMethod | None = None
    sold_at: datetime | None = None
    sold_to: str = ""
    lines: tuple[ConversionLine, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordPayout:
    reseller_id: int
    amount: Decimal
    note: str = ""
    paid_at: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaleFilters:
    period: SalesPeriod | None = None
    date_from: date | None = None
    date_to: date | None = None
    payment_method: PaymentMethod | None = None
    seller_id: int | None = None
    product_id: int | None = None
    status: SaleStatus | None = None
    search: str | None = None

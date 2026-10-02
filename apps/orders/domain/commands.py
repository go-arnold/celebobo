from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.orders.domain.enums import CancelReason, OrderStatus, PaymentMethod
from apps.orders.domain.pricing import CouponKind
from core.domain.values import UNSET, Maybe


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderLineInput:
    product_id: int
    quantity: int
    variant_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeliveryAddress:
    recipient: str
    phone: str
    line1: str
    quarter: str
    city: str
    country: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceOrder:
    lines: tuple[OrderLineInput, ...]
    payment_method: PaymentMethod
    address_id: int | None = None
    address: DeliveryAddress | None = None
    note: str = ""
    coupon_code: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelOrder:
    reason: CancelReason
    details: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignOrder:
    reseller_id: int
    note: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class DeclineAssignment:
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionOrder:
    to: OrderStatus
    note: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackOrder:
    number: str
    contact: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderFilters:
    status: OrderStatus | None = None
    unassigned: bool = False
    reseller_id: int | None = None
    payment_method: PaymentMethod | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ZoneFields:
    name: str
    fee: Decimal
    cities: tuple[str, ...] = ()
    free_threshold: Decimal | None = None
    delivery_estimate: str = ""
    is_default: bool = False
    is_active: bool = True
    position: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class ZoneChanges:
    name: Maybe[str] = UNSET
    fee: Maybe[Decimal] = UNSET
    cities: Maybe[tuple[str, ...]] = UNSET
    free_threshold: Maybe[Decimal | None] = UNSET
    delivery_estimate: Maybe[str] = UNSET
    is_default: Maybe[bool] = UNSET
    is_active: Maybe[bool] = UNSET
    position: Maybe[int] = UNSET


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponFields:
    code: str
    kind: CouponKind
    value: Decimal
    description: str = ""
    max_discount: Decimal | None = None
    min_subtotal: Decimal = Decimal(0)
    free_shipping: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    usage_limit: int | None = None
    per_user_limit: int | None = None
    is_active: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponChanges:
    code: Maybe[str] = UNSET
    kind: Maybe[CouponKind] = UNSET
    value: Maybe[Decimal] = UNSET
    description: Maybe[str] = UNSET
    max_discount: Maybe[Decimal | None] = UNSET
    min_subtotal: Maybe[Decimal] = UNSET
    free_shipping: Maybe[bool] = UNSET
    starts_at: Maybe[datetime | None] = UNSET
    ends_at: Maybe[datetime | None] = UNSET
    usage_limit: Maybe[int | None] = UNSET
    per_user_limit: Maybe[int | None] = UNSET
    is_active: Maybe[bool] = UNSET

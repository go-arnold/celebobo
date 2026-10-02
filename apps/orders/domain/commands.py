from dataclasses import dataclass
from datetime import date

from apps.orders.domain.enums import CancelReason, OrderStatus, PaymentMethod


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

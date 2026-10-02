from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.orders.domain.enums import OrderStatus, PaymentMethod


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteLineView:
    product_id: int
    variant_id: int | None
    name: str
    variant_label: str
    image: str
    unit_price: Decimal
    quantity: int
    total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteView:
    lines: tuple[QuoteLineView, ...]
    subtotal: Decimal
    shipping_fee: Decimal
    total: Decimal
    free_shipping_remaining: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class CartLineView:
    id: int
    product_id: int
    variant_id: int | None
    quantity: int
    available: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CartView:
    token: str | None
    lines: tuple[CartLineView, ...]
    quote: QuoteView


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderLineView:
    id: int
    product_id: int | None
    variant_id: int | None
    name: str
    variant_label: str
    image: str
    sku: str
    quantity: int
    unit_price: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class StatusEntry:
    status: OrderStatus
    at: datetime
    actor_role: str
    actor_name: str | None
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonBrief:
    id: int
    name: str
    email: str
    phone: str | None = None
    availability: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AddressSnapshot:
    recipient: str
    phone: str
    line1: str
    quarter: str
    city: str
    country: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderSummary:
    id: int
    number: str
    status: OrderStatus
    created_at: datetime
    total: Decimal
    items_count: int
    preview_name: str
    preview_image: str
    client_name: str
    reseller_name: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderDetail:
    summary: OrderSummary
    items: tuple[OrderLineView, ...]
    address: AddressSnapshot
    payment_method: PaymentMethod
    note: str
    subtotal: Decimal
    shipping_fee: Decimal
    cancel_reason: str
    history: tuple[StatusEntry, ...]
    allowed_transitions: tuple[OrderStatus, ...]
    client: PersonBrief
    reseller: PersonBrief | None
    conversation_id: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackedItem:
    name: str
    variant_label: str
    quantity: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackedStatus:
    status: OrderStatus
    at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackingView:
    number: str
    status: OrderStatus
    created_at: datetime
    total: Decimal
    items: tuple[TrackedItem, ...]
    history: tuple[TrackedStatus, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignableReseller:
    id: int
    name: str
    availability: str
    open_orders: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AdjustableItem:
    order_id: int
    order_number: str
    item_id: int
    client_id: int
    reseller_id: int | None
    name: str
    quantity: int
    unit_price: Decimal
    list_unit_price: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRef:
    id: int
    number: str
    client_id: int
    reseller_id: int | None
    status: OrderStatus
    total: Decimal

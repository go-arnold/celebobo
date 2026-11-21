from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.orders.domain.enums import DeliveryMethod, OrderStatus, PaymentMethod
from apps.orders.domain.pricing import ZonePricing


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
    free_shipping_remaining: Decimal | None
    discount: Decimal = Decimal("0.00")
    shipping_zone: str = ""
    delivery_estimate: str = ""
    coupon_code: str | None = None
    coupon_error: str | None = None
    points: Decimal = Decimal("0.00")
    points_available: Decimal = Decimal("0.00")
    delivery_method: DeliveryMethod = DeliveryMethod.DELIVERY
    pickup_address: str = ""
    # the zone is quoted on request: the fee is unknown until a reseller quotes it
    shipping_quote_required: bool = False
    pickup_available: bool = False


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
    discount: Decimal
    points: Decimal
    amount_paid: Decimal
    returned_quantity: int = 0
    returned_amount: Decimal = Decimal(0)


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
    # None when the viewer may not see it (resellers never get the client's e-mail)
    email: str | None
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
class SuggestedReseller:
    """The reseller suggested to staff assigning an order: the one who invited the client."""

    id: int
    name: str
    reason: str = "invited_client"
    invited_at: datetime | None = None


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
    client_id: int
    client_name: str
    reseller_name: str | None
    refund_status: str | None = None
    # internal, like client_id: the assigned reseller, to leave out a suggestion already followed
    reseller_id: int | None = None
    # staff who can assign only: the active reseller who invited the client
    suggested_reseller: SuggestedReseller | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AttemptView:
    at: datetime
    reason: str
    reason_label: str
    note: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RatingView:
    score: int
    comment: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class ResellerRatingRow:
    order_number: str
    client_name: str
    score: int
    comment: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RatingSummary:
    average: Decimal | None
    count: int


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
    discount: Decimal = Decimal("0.00")
    coupon_code: str = ""
    shipping_zone: str = ""
    delivery_method: DeliveryMethod = DeliveryMethod.DELIVERY
    pickup_address: str = ""
    delivery_estimate: str = ""
    awaiting_shipping_quote: bool = False
    refund_due: Decimal = Decimal("0.00")
    refunded_at: datetime | None = None
    refund_note: str = ""
    # shown to the client only (the back-office output leaves it out)
    delivery_code: str = ""
    delivery_code_attempts: int = 0
    delivery_code_locked: bool = False
    rating: RatingView | None = None
    can_rate: bool = False
    delivery_attempts: tuple[AttemptView, ...] = ()
    points: Decimal = Decimal("0.00")
    points_earned: Decimal | None = None
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
class QuotableOrder:
    order_id: int
    order_number: str
    client_id: int
    reseller_id: int | None
    city: str
    delivery_estimate: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderRef:
    id: int
    number: str
    client_id: int
    reseller_id: int | None
    status: OrderStatus
    total: Decimal


# how an order was handed over: who delivered it, when, and the delivery fee the client paid
@dataclass(frozen=True, slots=True, kw_only=True)
class OrderDelivery:
    id: int
    number: str
    status: OrderStatus
    reseller_id: int | None
    delivery_method: DeliveryMethod
    shipping_fee: Decimal
    delivered_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConvertibleItem:
    id: int
    product_id: int | None
    variant_id: int | None
    name: str
    variant_label: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ConvertibleOrder:
    id: int
    number: str
    status: OrderStatus
    client_id: int
    client_name: str
    reseller_id: int | None
    payment_method: PaymentMethod
    total: Decimal
    created_at: datetime
    items: tuple[ConvertibleItem, ...]
    # non-real money used on the order: a coupon or promotion, and points
    discount: Decimal = Decimal(0)
    points: Decimal = Decimal(0)

    # paid only in cash or Mobile Money: no points, no coupon (owner rule on non-real money)
    @property
    def real_money_only(self) -> bool:
        return self.discount == 0 and self.points == 0


@dataclass(frozen=True, slots=True, kw_only=True)
class ClientOrderTotals:
    count: int
    total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingZoneView:
    id: int
    name: str
    cities: tuple[str, ...]
    fee: Decimal
    free_threshold: Decimal | None
    delivery_estimate: str
    is_default: bool
    is_active: bool
    position: int
    pricing: ZonePricing = ZonePricing.FLAT
    pickup_address: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponView:
    id: int
    code: str
    description: str
    kind: str
    value: Decimal
    max_discount: Decimal | None
    min_subtotal: Decimal
    free_shipping: bool
    starts_at: datetime | None
    ends_at: datetime | None
    usage_limit: int | None
    per_user_limit: int | None
    is_active: bool
    uses: int
    discount_total: Decimal
    created_at: datetime

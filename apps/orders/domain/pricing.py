from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class CouponKind(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingRules:
    free_threshold: Decimal | None
    flat_fee: Decimal
    zone: str = ""
    delivery_estimate: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponTerms:
    code: str
    kind: CouponKind
    value: Decimal
    max_discount: Decimal | None = None
    free_shipping: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class QuoteLine:
    unit_price: Decimal
    quantity: int
    free_shipping: bool
    shipping_fee: Decimal | None

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True, kw_only=True)
class Quote:
    subtotal: Decimal
    discount: Decimal
    shipping_fee: Decimal
    total: Decimal
    free_shipping_remaining: Decimal | None


def quote(
    lines: Sequence[QuoteLine], rules: ShippingRules, coupon: CouponTerms | None = None
) -> Quote:
    subtotal = sum((line.total for line in lines), ZERO)
    discount = discount_for(coupon, subtotal) if coupon else ZERO
    shipping = ZERO if coupon and coupon.free_shipping else _shipping_fee(lines, subtotal, rules)
    remaining = (
        max(rules.free_threshold - subtotal, ZERO) if rules.free_threshold is not None else None
    )
    return Quote(
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping,
        total=subtotal - discount + shipping,
        free_shipping_remaining=remaining,
    )


def discount_for(coupon: CouponTerms, subtotal: Decimal) -> Decimal:
    if coupon.kind is CouponKind.PERCENT:
        amount = (subtotal * coupon.value / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if coupon.max_discount is not None:
            amount = min(amount, coupon.max_discount)
    else:
        amount = coupon.value
    return min(amount, subtotal)


def _shipping_fee(lines: Sequence[QuoteLine], subtotal: Decimal, rules: ShippingRules) -> Decimal:
    payable = [line for line in lines if not line.free_shipping]
    if not payable or (rules.free_threshold is not None and subtotal >= rules.free_threshold):
        return ZERO
    return max(
        line.shipping_fee if line.shipping_fee is not None else rules.flat_fee for line in payable
    )

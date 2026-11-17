from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
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
    member_free: bool = False


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
    lines: Sequence[QuoteLine],
    rules: ShippingRules,
    coupon: CouponTerms | None = None,
    *,
    member: bool = False,
) -> Quote:
    subtotal = sum((line.total for line in lines), ZERO)
    discount = discount_for(coupon, subtotal) if coupon else ZERO
    free = member or (coupon is not None and coupon.free_shipping)
    shipping = ZERO if free else _shipping_fee(lines, subtotal, rules)
    remaining = (
        max(rules.free_threshold - subtotal, ZERO)
        if rules.free_threshold is not None and not member
        else None
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


@dataclass(frozen=True, slots=True)
class LineAmounts:
    discount: Decimal
    cashback: Decimal
    paid: Decimal


def spread(amount: Decimal, weights: Sequence[Decimal]) -> list[Decimal]:
    """Splits ``amount`` in proportion to ``weights``, to the cent; the shares add up exactly.

    Each share is rounded down, then the cents left go to the largest remainders (first line on a
    tie). No share exceeds its weight while ``amount`` is at most their sum.
    """
    total = sum(weights, ZERO)
    if amount <= 0 or total <= 0:
        return [ZERO for _ in weights]
    exact = [amount * weight / total for weight in weights]
    shares = [value.quantize(CENT, rounding=ROUND_DOWN) for value in exact]
    left = int((amount - sum(shares, ZERO)) / CENT)
    by_remainder = sorted(
        range(len(weights)), key=lambda index: (shares[index] - exact[index], index)
    )
    for index in by_remainder[:left]:
        shares[index] += CENT
    return shares


def line_amounts(
    totals: Sequence[Decimal], *, discount: Decimal, cashback: Decimal
) -> list[LineAmounts]:
    """What each order line really cost the client, once the order's coupon and cashback are spread.

    The coupon is spread over the line totals; the cashback over what is left after the coupon,
    since it pays the products after the discount. Shipping is not part of any line.
    """
    discounts = spread(discount, totals)
    after_coupon = [line - share for line, share in zip(totals, discounts, strict=True)]
    cashbacks = spread(cashback, after_coupon)
    return [
        LineAmounts(discount=coupon, cashback=credit, paid=rest - credit)
        for coupon, credit, rest in zip(discounts, cashbacks, after_coupon, strict=True)
    ]


def returned_amounts(
    line: LineAmounts, *, quantity: int, returned: int, returning: int, already: LineAmounts
) -> LineAmounts:
    """The share of a line's amounts that goes with ``returning`` of its ``quantity`` units.

    Each partial return takes its proportion rounded down; the return of the last units takes
    whatever is left, so all the returns of a line add up exactly to its amounts.
    """
    if returned + returning >= quantity:
        return LineAmounts(
            discount=line.discount - already.discount,
            cashback=line.cashback - already.cashback,
            paid=line.paid - already.paid,
        )

    def part(amount: Decimal) -> Decimal:
        return (amount * returning / quantity).quantize(CENT, rounding=ROUND_DOWN)

    return LineAmounts(
        discount=part(line.discount), cashback=part(line.cashback), paid=part(line.paid)
    )

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


class CouponKind(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class ZonePricing(StrEnum):
    # the zone's fee, waived from its threshold
    FLAT = "flat"
    # no fee at checkout: a reseller quotes it in the order discussion, the client accepts it
    # or cancels
    QUOTE = "quote"
    # the client collects the order at the shop, free of charge
    PICKUP = "pickup"

    @property
    def label(self) -> str:
        return {"flat": "Tarif fixe", "quote": "Sur devis", "pickup": "Retrait sur place"}[
            self.value
        ]


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingRules:
    free_threshold: Decimal | None
    flat_fee: Decimal
    zone: str = ""
    delivery_estimate: str = ""
    pricing: ZonePricing = ZonePricing.FLAT
    pickup_address: str = ""

    @property
    def priced_later(self) -> bool:
        return self.pricing is ZonePricing.QUOTE


@dataclass(frozen=True, slots=True, kw_only=True)
class CouponTerms:
    code: str
    kind: CouponKind
    value: Decimal
    max_discount: Decimal | None = None
    free_shipping: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignLine:
    product_id: int
    total: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class CampaignOffer:
    """The Cagnotte operation running when the order is placed (loyalty policy, Cagnotte).

    ``discounts``: per line, the immediate discount (``discount`` operations only); ``advantage``:
    the cashback or boosted points the eligible lines would bring, as an estimate (the final amount
    is computed on delivery from what the client really paid).
    """

    campaign_id: int
    name: str
    kind: str
    percent: Decimal
    discounts: tuple[Decimal, ...]
    advantage: Decimal = ZERO

    @property
    def discount(self) -> Decimal:
        return sum(self.discounts, ZERO)


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
    campaign_discount: Decimal = ZERO,
) -> Quote:
    """``discount`` is the Cagnotte discount plus the coupon, which applies to what is left."""
    subtotal = sum((line.total for line in lines), ZERO)
    campaign = min(campaign_discount, subtotal)
    discount = campaign + (discount_for(coupon, subtotal - campaign) if coupon else ZERO)
    # pickup is free and a quoted zone has no fee until the client accepts the reseller's quote
    flat = rules.pricing is ZonePricing.FLAT
    free = not flat or (coupon is not None and coupon.free_shipping)
    shipping = ZERO if free else _shipping_fee(lines, subtotal, rules)
    remaining = (
        max(rules.free_threshold - subtotal, ZERO)
        if flat and rules.free_threshold is not None
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
    points: Decimal
    paid: Decimal
    # the line's share of the store credit (avoir) used on the order
    credit: Decimal = ZERO
    # the part of ``discount`` that is the Cagnotte discount
    campaign: Decimal = ZERO


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
    totals: Sequence[Decimal],
    *,
    discount: Decimal,
    points: Decimal,
    credit: Decimal = ZERO,
    campaign: Sequence[Decimal] | None = None,
) -> list[LineAmounts]:
    """What each order line really cost the client, once the order's coupon, points and store
    credit are spread.

    The coupon is spread over the line totals; the points over what is left after the coupon,
    since it pays the products after the discount; the store credit over what is left after the
    points (the part of it beyond the products pays the delivery, which is not part of any line).

    A Cagnotte discount (``campaign``) belongs to its lines; ``discount`` includes it, and the
    coupon (the rest) is spread over what is left of each line.
    """
    campaign_parts = list(campaign) if campaign is not None else [ZERO for _ in totals]
    after_campaign = [line - part for line, part in zip(totals, campaign_parts, strict=True)]
    coupons = spread(discount - sum(campaign_parts, ZERO), after_campaign)
    discounts = [part + coupon for part, coupon in zip(campaign_parts, coupons, strict=True)]
    after_coupon = [line - share for line, share in zip(totals, discounts, strict=True)]
    point_parts = spread(points, after_coupon)
    after_points = [rest - part for rest, part in zip(after_coupon, point_parts, strict=True)]
    credit_parts = spread(min(credit, sum(after_points, ZERO)), after_points)
    return [
        LineAmounts(discount=coupon, points=part, paid=rest - avoir, credit=avoir, campaign=own)
        for coupon, part, avoir, rest, own in zip(
            discounts, point_parts, credit_parts, after_points, campaign_parts, strict=True
        )
    ]


def products_credit(credit: Decimal, products_due: Decimal) -> Decimal:
    """The part of the store credit that pays the products; the rest pays the delivery."""
    return min(credit, max(products_due, ZERO))


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
            points=line.points - already.points,
            paid=line.paid - already.paid,
            credit=line.credit - already.credit,
        )

    def part(amount: Decimal) -> Decimal:
        return (amount * returning / quantity).quantize(CENT, rounding=ROUND_DOWN)

    return LineAmounts(
        discount=part(line.discount),
        points=part(line.points),
        paid=part(line.paid),
        credit=part(line.credit),
    )

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.sales.domain.enums import CommissionRule

CENT = Decimal("0.01")
ZERO = Decimal("0.00")

# reseller commission, rules decided by the owner on 16 Nov 2026 (docs/business/05)
PAID_SHARE = Decimal("0.10")
MARGIN_SHARE = Decimal("0.50")
PARTNER_GAIN_SHARE = Decimal("0.20")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True, kw_only=True)
class CommissionLine:
    # the amount paid for the line, in real money
    paid: Decimal
    quantity: int
    unit_cost: Decimal | None
    partner: bool = False
    partner_gain: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Commission:
    amount: Decimal
    rule: CommissionRule


# Celebobo product: min(10 % of the paid amount, 50 % of the gross margin), nothing on a margin
# <= 0, 10 % when the cost is unknown. Partner product: min(10 % of the paid amount, 20 % of
# Celebobo's gain). Each amount is rounded to the cent before comparing.
def line_commission(line: CommissionLine) -> Commission:
    paid_share = cents(line.paid * PAID_SHARE)
    if line.partner:
        gain = (line.partner_gain or ZERO) * line.quantity
        return _lowest(paid_share, cents(max(gain, ZERO) * PARTNER_GAIN_SHARE), partner=True)
    if line.unit_cost is None:
        return Commission(paid_share, CommissionRule.UNKNOWN_COST)
    margin = line.paid - line.unit_cost * line.quantity
    if margin <= 0:
        return Commission(ZERO, CommissionRule.MARGIN)
    return _lowest(paid_share, cents(margin * MARGIN_SHARE), partner=False)


def _lowest(paid_share: Decimal, cap: Decimal, *, partner: bool) -> Commission:
    if paid_share <= cap:
        return Commission(paid_share, CommissionRule.PAID)
    return Commission(cap, CommissionRule.PARTNER_GAIN if partner else CommissionRule.MARGIN)


def proportional_reversal(earned: Decimal, refunded: Decimal, total: Decimal) -> Decimal:
    if total <= 0 or earned <= 0:
        return ZERO
    return cents(earned * min(refunded, total) / total)


def refundable(total: Decimal, already_refunded: Decimal) -> Decimal:
    return max(total - already_refunded, ZERO)


def profit_for(unit_price: Decimal, unit_cost: Decimal | None, quantity: int) -> Decimal | None:
    if unit_cost is None:
        return None
    return cents((unit_price - unit_cost) * quantity)

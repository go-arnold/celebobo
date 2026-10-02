from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def commission_for(amount: Decimal, rate: Decimal) -> Decimal:
    return cents(amount * rate)


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

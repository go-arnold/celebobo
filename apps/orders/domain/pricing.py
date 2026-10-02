from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True, kw_only=True)
class ShippingRules:
    free_threshold: Decimal
    flat_fee: Decimal


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
    shipping_fee: Decimal
    total: Decimal
    free_shipping_remaining: Decimal


def quote(lines: Sequence[QuoteLine], rules: ShippingRules) -> Quote:
    subtotal = sum((line.total for line in lines), ZERO)
    shipping = _shipping_fee(lines, subtotal, rules)
    return Quote(
        subtotal=subtotal,
        shipping_fee=shipping,
        total=subtotal + shipping,
        free_shipping_remaining=max(rules.free_threshold - subtotal, ZERO),
    )


def _shipping_fee(lines: Sequence[QuoteLine], subtotal: Decimal, rules: ShippingRules) -> Decimal:
    payable = [line for line in lines if not line.free_shipping]
    if not payable or subtotal >= rules.free_threshold:
        return ZERO
    return max(
        line.shipping_fee if line.shipping_fee is not None else rules.flat_fee for line in payable
    )

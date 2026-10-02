from collections.abc import Sequence

from apps.catalog.domain.queries import StockLine
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import OrderLineInput
from apps.orders.domain.errors import EmptyOrder, TooManyLines
from apps.orders.domain.pricing import QuoteLine, ShippingRules, quote
from apps.orders.domain.read_models import QuoteLineView, QuoteView
from apps.orders.services.contracts import Inventory


class PricingService:
    def __init__(self, inventory: Inventory, rules: ShippingRules, *, max_lines: int) -> None:
        self._inventory = inventory
        self._rules = rules
        self._max_lines = max_lines

    def price(self, lines: Sequence[OrderLineInput]) -> tuple[QuoteView, list[PricedLine]]:
        if not lines:
            raise EmptyOrder
        if len(lines) > self._max_lines:
            raise TooManyLines(self._max_lines)
        priced = self._inventory.price([stock_line(line) for line in lines])
        return self.view(priced), priced

    def view(self, priced: Sequence[PricedLine]) -> QuoteView:
        result = quote(
            [
                QuoteLine(
                    unit_price=line.unit_price,
                    quantity=line.quantity,
                    free_shipping=line.free_shipping,
                    shipping_fee=line.shipping_fee,
                )
                for line in priced
            ],
            self._rules,
        )
        return QuoteView(
            lines=tuple(
                QuoteLineView(
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    name=line.name,
                    variant_label=line.variant_label,
                    image=line.image,
                    unit_price=line.unit_price,
                    quantity=line.quantity,
                    total=line.total,
                )
                for line in priced
            ),
            subtotal=result.subtotal,
            shipping_fee=result.shipping_fee,
            total=result.total,
            free_shipping_remaining=result.free_shipping_remaining,
        )


def stock_line(line: OrderLineInput) -> StockLine:
    return StockLine(product_id=line.product_id, variant_id=line.variant_id, quantity=line.quantity)

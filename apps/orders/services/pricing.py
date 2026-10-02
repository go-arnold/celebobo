from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from apps.catalog.domain.queries import StockLine
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import OrderLineInput
from apps.orders.domain.errors import CouponRejected, EmptyOrder, TooManyLines
from apps.orders.domain.pricing import ZERO, CouponTerms, QuoteLine, quote
from apps.orders.domain.read_models import QuoteLineView, QuoteView
from apps.orders.models import Coupon
from apps.orders.services.contracts import Inventory
from apps.orders.services.coupons import CouponService
from apps.orders.services.shipping import ShippingResolver


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingContext:
    city: str | None = None
    coupon_code: str | None = None
    user_id: int | None = None
    strict: bool = False
    lock: bool = False


DEFAULT_CONTEXT = PricingContext()


@dataclass(frozen=True, slots=True)
class PricedQuote:
    view: QuoteView
    lines: list[PricedLine]
    coupon: Coupon | None


class PricingService:
    def __init__(
        self,
        inventory: Inventory,
        shipping: ShippingResolver,
        coupons: CouponService,
        *,
        max_lines: int,
    ) -> None:
        self._inventory = inventory
        self._shipping = shipping
        self._coupons = coupons
        self._max_lines = max_lines

    def price(
        self, lines: Sequence[OrderLineInput], context: PricingContext = DEFAULT_CONTEXT
    ) -> PricedQuote:
        if not lines:
            raise EmptyOrder
        if len(lines) > self._max_lines:
            raise TooManyLines(self._max_lines)
        priced = self._inventory.price([stock_line(line) for line in lines])
        view, coupon = self.view(priced, context)
        return PricedQuote(view, priced, coupon)

    def view(
        self, priced: Sequence[PricedLine], context: PricingContext = DEFAULT_CONTEXT
    ) -> tuple[QuoteView, Coupon | None]:
        quote_lines = [
            QuoteLine(
                unit_price=line.unit_price,
                quantity=line.quantity,
                free_shipping=line.free_shipping,
                shipping_fee=line.shipping_fee,
            )
            for line in priced
        ]
        subtotal = sum((line.total for line in quote_lines), ZERO)
        coupon, terms, error = self._coupon(context, subtotal)
        rules = self._shipping.rules_for(context.city)
        result = quote(quote_lines, rules, terms)
        return (
            QuoteView(
                lines=tuple(_line_view(line) for line in priced),
                subtotal=result.subtotal,
                discount=result.discount,
                shipping_fee=result.shipping_fee,
                total=result.total,
                free_shipping_remaining=result.free_shipping_remaining,
                shipping_zone=rules.zone,
                delivery_estimate=rules.delivery_estimate,
                coupon_code=terms.code if terms else None,
                coupon_error=error,
            ),
            coupon,
        )

    def _coupon(
        self, context: PricingContext, subtotal: Decimal
    ) -> tuple[Coupon | None, CouponTerms | None, str | None]:
        if not context.coupon_code:
            return None, None, None
        try:
            coupon, terms = self._coupons.terms(
                context.coupon_code,
                subtotal=subtotal,
                user_id=context.user_id,
                lock=context.lock,
            )
        except CouponRejected as error:
            if context.strict:
                raise
            return None, None, str(error.detail)
        return coupon, terms, None


def _line_view(line: PricedLine) -> QuoteLineView:
    return QuoteLineView(
        product_id=line.product_id,
        variant_id=line.variant_id,
        name=line.name,
        variant_label=line.variant_label,
        image=line.image,
        unit_price=line.unit_price,
        quantity=line.quantity,
        total=line.total,
    )


def stock_line(line: OrderLineInput) -> StockLine:
    return StockLine(product_id=line.product_id, variant_id=line.variant_id, quantity=line.quantity)

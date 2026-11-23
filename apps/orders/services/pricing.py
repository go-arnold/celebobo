from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from apps.catalog.domain.queries import StockLine
from apps.catalog.domain.read_models import PricedLine
from apps.orders.adapters.gateways import NoCampaigns, NoCreditWallet
from apps.orders.domain.commands import OrderLineInput
from apps.orders.domain.enums import DeliveryMethod
from apps.orders.domain.errors import (
    CouponRejected,
    EmptyOrder,
    PointsUnavailable,
    StoreCreditUnavailable,
    TooManyLines,
)
from apps.orders.domain.pricing import (
    ZERO,
    CampaignLine,
    CampaignOffer,
    CouponTerms,
    QuoteLine,
    quote,
)
from apps.orders.domain.read_models import QuoteLineView, QuoteView
from apps.orders.models import Coupon
from apps.orders.services.contracts import (
    AddressBook,
    CampaignOffers,
    CreditWallet,
    Inventory,
    Wallet,
)
from apps.orders.services.coupons import CouponService
from apps.orders.services.shipping import ShippingResolver


@dataclass(frozen=True, slots=True, kw_only=True)
class PricingContext:
    city: str | None = None
    coupon_code: str | None = None
    user_id: int | None = None
    strict: bool = False
    lock: bool = False
    # points the client asks to use; the quote applies what their balance and the items allow
    points: Decimal = ZERO
    # store credit the client asks to use: up to their balance and what is left to pay, delivery
    # included
    store_credit: Decimal = ZERO
    pickup: bool = False


DEFAULT_CONTEXT = PricingContext()


@dataclass(frozen=True, slots=True)
class PricedQuote:
    view: QuoteView
    lines: list[PricedLine]
    coupon: Coupon | None
    campaign: CampaignOffer | None = None


class PricingService:
    def __init__(
        self,
        inventory: Inventory,
        shipping: ShippingResolver,
        coupons: CouponService,
        wallet: Wallet,
        *,
        addresses: AddressBook,
        max_lines: int,
        credit: CreditWallet | None = None,
        campaigns: CampaignOffers | None = None,
    ) -> None:
        self._inventory = inventory
        self._shipping = shipping
        self._coupons = coupons
        self._wallet = wallet
        self._credit = credit or NoCreditWallet()
        self._campaigns = campaigns or NoCampaigns()
        self._addresses = addresses
        self._max_lines = max_lines

    def price(
        self, lines: Sequence[OrderLineInput], context: PricingContext = DEFAULT_CONTEXT
    ) -> PricedQuote:
        if not lines:
            raise EmptyOrder
        if len(lines) > self._max_lines:
            raise TooManyLines(self._max_lines)
        priced = self._inventory.price([stock_line(line) for line in lines], lock=context.lock)
        campaign = self._campaign(priced)
        view, coupon = self.view(priced, context, campaign=campaign)
        return PricedQuote(view, priced, coupon, campaign)

    def _campaign(self, priced: Sequence[PricedLine]) -> CampaignOffer | None:
        return self._campaigns.offer(
            [CampaignLine(product_id=line.product_id, total=line.total) for line in priced]
        )

    def view(
        self,
        priced: Sequence[PricedLine],
        context: PricingContext = DEFAULT_CONTEXT,
        *,
        campaign: CampaignOffer | None = None,
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
        # the cart priced alone looks up the running Cagnotte operation itself
        if campaign is None:
            campaign = self._campaign(priced)
        campaign_discount = campaign.discount if campaign else ZERO
        # the coupon applies to what is left after the Cagnotte discount
        coupon, terms, error = self._coupon(context, subtotal - campaign_discount)
        rules = self._shipping.rules_for(self._city(context), pickup=context.pickup)
        result = quote(quote_lines, rules, terms, campaign_discount=campaign_discount)
        available = (
            self._wallet.usable(
                context.user_id, result.subtotal - result.discount, lock=context.lock
            )
            if context.user_id is not None
            else ZERO
        )
        if context.strict and context.points > available:
            raise PointsUnavailable
        points = min(context.points, available)
        due = result.total - points
        credit_available = (
            self._credit.usable(context.user_id, due, lock=context.lock)
            if context.user_id is not None
            else ZERO
        )
        # asking more than the total is simply capped; asking more than the balance is refused
        if context.strict and context.store_credit > credit_available and credit_available < due:
            raise StoreCreditUnavailable
        store_credit = min(context.store_credit, credit_available)
        return (
            QuoteView(
                lines=tuple(_line_view(line) for line in priced),
                subtotal=result.subtotal,
                discount=result.discount,
                shipping_fee=result.shipping_fee,
                total=due - store_credit,
                free_shipping_remaining=result.free_shipping_remaining,
                shipping_zone=rules.zone,
                delivery_estimate=rules.delivery_estimate,
                coupon_code=terms.code if terms else None,
                coupon_error=error,
                points=points,
                points_available=available,
                store_credit=store_credit,
                store_credit_available=credit_available,
                delivery_method=DeliveryMethod.PICKUP
                if context.pickup
                else DeliveryMethod.DELIVERY,
                pickup_address=rules.pickup_address,
                shipping_quote_required=rules.priced_later,
                pickup_available=self._shipping.pickup_available(),
                campaign_id=campaign.campaign_id if campaign else None,
                campaign_name=campaign.name if campaign else "",
                campaign_kind=campaign.kind if campaign else "",
                campaign_percent=campaign.percent if campaign else None,
                campaign_discount=campaign_discount,
                campaign_advantage=campaign.advantage if campaign else ZERO,
            ),
            coupon,
        )

    # a signed-in client without a city yet is priced for their default address
    def _city(self, context: PricingContext) -> str | None:
        if context.city or context.user_id is None:
            return context.city
        return self._addresses.default_city(context.user_id)

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

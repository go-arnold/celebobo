from apps.catalog.domain.queries import StockSource
from apps.orders.domain.commands import DeliveryAddress, PlaceOrder
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import AddressRequired
from apps.orders.models import Order
from apps.orders.repositories import OrderRepository
from apps.orders.services.contracts import AddressBook, Inventory
from apps.orders.services.coupons import CouponService
from apps.orders.services.pricing import PricingContext, PricingService, stock_line
from core.domain.actor import Actor, Role

ORDER_SOURCE = "order"


class CheckoutService:
    def __init__(
        self,
        orders: OrderRepository,
        pricing: PricingService,
        inventory: Inventory,
        addresses: AddressBook,
        coupons: CouponService,
    ) -> None:
        self._orders = orders
        self._pricing = pricing
        self._inventory = inventory
        self._addresses = addresses
        self._coupons = coupons

    def place(self, client_id: int, command: PlaceOrder) -> Order:
        address = self._address(client_id, command)
        priced_quote = self._pricing.price(
            command.lines,
            PricingContext(
                city=address.city,
                coupon_code=command.coupon_code,
                user_id=client_id,
                strict=True,
                lock=True,
            ),
        )
        quote, priced = priced_quote.view, priced_quote.lines
        order = self._orders.create(
            client_id=client_id,
            status=OrderStatus.PENDING.value,
            recipient=address.recipient,
            phone=address.phone,
            line1=address.line1,
            quarter=address.quarter,
            city=address.city,
            country=address.country,
            payment_method=command.payment_method.value,
            note=" ".join(command.note.split()),
            subtotal=quote.subtotal,
            discount=quote.discount,
            coupon_code=quote.coupon_code or "",
            shipping_zone=quote.shipping_zone,
            shipping_fee=quote.shipping_fee,
            total=quote.total,
        )
        if priced_quote.coupon is not None:
            self._coupons.redeem(
                priced_quote.coupon, order, user_id=client_id, amount=quote.discount
            )
        self._orders.add_items(
            order,
            (
                {
                    "product_id": line.product_id,
                    "variant_id": line.variant_id,
                    "product_name": line.name,
                    "variant_label": line.variant_label,
                    "product_image": line.image,
                    "sku": line.sku,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "list_unit_price": line.unit_price,
                }
                for line in priced
            ),
        )
        self._inventory.reserve(
            [stock_line(line) for line in command.lines],
            StockSource(kind=ORDER_SOURCE, id=order.pk, actor_id=client_id),
        )
        self._orders.record(
            order,
            previous=None,
            status=OrderStatus.PENDING,
            actor_id=client_id,
            actor_role=Role.CLIENT.value,
        )
        return order

    def _address(self, client_id: int, command: PlaceOrder) -> DeliveryAddress:
        if command.address_id is not None:
            return self._addresses.snapshot(client_id, command.address_id)
        if command.address is None:
            raise AddressRequired
        return command.address


def actor_role(actor: Actor) -> str:
    return actor.role.value if actor.role is not Role.ANONYMOUS else Role.SYSTEM.value

from decimal import Decimal

from apps.orders.domain.errors import (
    InvalidShippingQuote,
    NotAssignedToYou,
    OrderNotFound,
    ShippingNotQuotable,
)
from apps.orders.domain.read_models import QuotableOrder
from apps.orders.models import Order
from apps.orders.repositories import OrderRepository
from apps.orders.services.checkout import actor_role
from core.domain.actor import Actor


class ShippingQuoteService:
    """The fee of an order placed in a zone quoted on request.

    The reseller quotes it in the order discussion; once the client accepts, it is added to the
    order and can no longer change.
    """

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def quotable(self, actor: Actor, order_id: int) -> QuotableOrder:
        order = self._load(order_id, for_update=False)
        if not (actor.is_staff or actor.owns(order.assigned_reseller_id)):
            raise NotAssignedToYou
        return QuotableOrder(
            order_id=order.pk,
            order_number=order.number,
            client_id=order.client_id,
            reseller_id=order.assigned_reseller_id,
            city=order.city,
            delivery_estimate=order.delivery_estimate,
        )

    def accept(self, actor: Actor, order_id: int, fee: Decimal, delivery_estimate: str) -> Order:
        if fee < 0:
            raise InvalidShippingQuote
        order = self._load(order_id, for_update=True)
        order.shipping_fee = fee
        order.total = order.subtotal - order.discount - order.points + fee
        order.delivery_estimate = delivery_estimate or order.delivery_estimate
        order.awaiting_shipping_quote = False
        self._orders.save(
            order,
            fields=("shipping_fee", "total", "delivery_estimate", "awaiting_shipping_quote"),
        )
        self._orders.record(
            order,
            previous=order.order_status,
            status=order.order_status,
            actor_id=actor.user_id,
            actor_role=actor_role(actor),
            note=f"Frais de livraison acceptés : {fee} $",
        )
        return order

    def _load(self, order_id: int, *, for_update: bool) -> Order:
        order = self._orders.get(order_id, for_update=for_update)
        if order is None:
            raise OrderNotFound
        if not order.awaiting_shipping_quote or order.order_status.is_final:
            raise ShippingNotQuotable
        return order

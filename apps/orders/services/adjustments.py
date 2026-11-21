from dataclasses import dataclass
from decimal import Decimal

from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import (
    InvalidProposedPrice,
    ItemNotAdjustable,
    NotAssignedToYou,
    OrderItemNotFound,
    OrderNotFound,
)
from apps.orders.domain.pricing import line_amounts
from apps.orders.domain.read_models import AdjustableItem
from apps.orders.models import Order, OrderItem
from apps.orders.repositories import OrderRepository
from core.domain.actor import Actor

ADJUSTABLE_STATUSES = frozenset({OrderStatus.ASSIGNED, OrderStatus.CONFIRMED})


@dataclass(frozen=True, slots=True)
class Repricing:
    order: Order
    item: OrderItem
    previous_price: Decimal


class AdjustmentService:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def adjustable(self, actor: Actor, order_id: int, item_id: int) -> AdjustableItem:
        order, item = self._load(order_id, item_id, for_update=False)
        if not (actor.is_staff or actor.owns(order.assigned_reseller_id)):
            raise NotAssignedToYou
        return AdjustableItem(
            order_id=order.pk,
            order_number=order.number,
            item_id=item.pk,
            client_id=order.client_id,
            reseller_id=order.assigned_reseller_id,
            name=item.product_name,
            quantity=item.quantity,
            unit_price=item.unit_price,
            list_unit_price=item.list_unit_price,
        )

    def apply(self, order_id: int, item_id: int, price: Decimal) -> Repricing:
        order, item = self._load(order_id, item_id, for_update=True)
        if price <= 0 or price > item.list_unit_price:
            raise InvalidProposedPrice
        previous = item.unit_price
        items = self._orders.items(order)
        for line in items:
            if line.pk == item.pk:
                line.unit_price = price
        order.subtotal = sum((line.total for line in items), Decimal(0))
        order.discount = min(order.discount, order.subtotal)
        order.points = min(order.points, order.subtotal - order.discount)
        order.total = order.subtotal - order.discount - order.points + order.shipping_fee
        # the new price changes every line's share of the coupon and points
        shares = line_amounts(
            [line.total for line in items], discount=order.discount, points=order.points
        )
        for line, share in zip(items, shares, strict=True):
            line.discount, line.points, line.amount_paid = (
                share.discount,
                share.points,
                share.paid,
            )
        self._orders.reprice(item_id=item.pk, price=price, items=items)
        self._orders.save(order, fields=("subtotal", "discount", "points", "total"))
        item.unit_price = price
        return Repricing(order, item, previous)

    def _load(self, order_id: int, item_id: int, *, for_update: bool) -> tuple[Order, OrderItem]:
        order = self._orders.get(order_id, for_update=for_update)
        if order is None:
            raise OrderNotFound
        item = self._orders.item(order, item_id)
        if item is None:
            raise OrderItemNotFound
        if order.order_status not in ADJUSTABLE_STATUSES:
            raise ItemNotAdjustable
        return order, item

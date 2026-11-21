from dataclasses import dataclass

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.orders.domain.commands import ReturnLine
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import InvalidReturnQuantity, LineNotReturnable, OrderItemNotFound
from apps.orders.domain.pricing import LineAmounts, returned_amounts
from apps.orders.models import Order, OrderItem, OrderLineReturn
from apps.orders.repositories import OrderRepository
from apps.orders.services.checkout import ORDER_SOURCE
from apps.orders.services.contracts import Inventory
from core.domain.actor import Actor


@dataclass(frozen=True, slots=True)
class LineReturned:
    item: OrderItem
    record: OrderLineReturn
    share: LineAmounts
    order_fully_returned: bool


class LineReturnService:
    def __init__(self, orders: OrderRepository, inventory: Inventory) -> None:
        self._orders = orders
        self._inventory = inventory

    # some units of one line come back after delivery: stock is released and the return keeps
    # its share of the line amounts, which sales and points follow
    def return_line(
        self, order: Order, item_id: int, actor: Actor, command: ReturnLine
    ) -> LineReturned:
        if order.order_status is not OrderStatus.DELIVERED:
            raise LineNotReturnable
        item = self._orders.item(order, item_id, for_update=True)
        if item is None:
            raise OrderItemNotFound
        remaining = item.quantity - item.returned_quantity
        if not 1 <= command.quantity <= remaining:
            raise InvalidReturnQuantity(remaining)
        share = returned_amounts(
            LineAmounts(discount=item.discount, points=item.points, paid=item.amount_paid),
            quantity=item.quantity,
            returned=item.returned_quantity,
            returning=command.quantity,
            already=self._orders.returned_amounts(item),
        )
        record = self._orders.add_return(
            order=order,
            item=item,
            quantity=command.quantity,
            amount_paid=share.paid,
            discount=share.discount,
            points=share.points,
            reason=" ".join(command.reason.split())[:500],
            actor_id=actor.user_id,
        )
        item.returned_quantity += command.quantity
        self._orders.save_item(item, fields=("returned_quantity",))
        if item.product_id is not None:
            self._inventory.release(
                [
                    StockLine(
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        quantity=command.quantity,
                    )
                ],
                StockSource(kind=ORDER_SOURCE, id=order.pk, actor_id=actor.user_id),
                reason=StockReason.RETURN,
                note=f"Retour partiel de la commande {order.number}",
            )
        fully = all(line.returned_quantity >= line.quantity for line in self._orders.items(order))
        return LineReturned(item, record, share, fully)

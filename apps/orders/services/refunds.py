from collections.abc import Callable
from datetime import datetime

from apps.orders.domain.commands import RecordRefund
from apps.orders.domain.errors import NoRefundDue
from apps.orders.models import Order
from apps.orders.repositories import OrderRepository
from apps.orders.services.checkout import actor_role
from core.domain.actor import Actor


class RefundService:
    """Money owed back after a paid order was cancelled: staff record that it was given back."""

    def __init__(self, orders: OrderRepository, *, clock: Callable[[], datetime]) -> None:
        self._orders = orders
        self._clock = clock

    def record(self, order: Order, actor: Actor, command: RecordRefund) -> Order:
        if order.refund_due <= 0 or order.refunded_at is not None:
            raise NoRefundDue
        order.refunded_at = self._clock()
        order.refund_note = " ".join(command.note.split())[:200]
        self._orders.save(order, fields=("refunded_at", "refund_note"))
        note = f"Remboursement de {order.refund_due} $ effectué"
        self._orders.record(
            order,
            previous=order.order_status,
            status=order.order_status,
            actor_id=actor.user_id,
            actor_role=actor_role(actor),
            note=f"{note} — {order.refund_note}" if order.refund_note else note,
        )
        return order

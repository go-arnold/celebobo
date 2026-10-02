from dataclasses import dataclass

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.orders.domain.commands import AssignOrder, CancelOrder, DeclineAssignment, TransitionOrder
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.errors import AssignmentClosed, NotAssignedToYou, ResellerNotFound
from apps.orders.domain.state_machine import OrderState, OrderStateMachine
from apps.orders.models import Order
from apps.orders.repositories import OrderRepository
from apps.orders.services.checkout import ORDER_SOURCE, actor_role
from apps.orders.services.contracts import Inventory, ResellerDirectory
from core.domain.actor import Actor

REASSIGNABLE = frozenset(
    {OrderStatus.PENDING, OrderStatus.ASSIGNED, OrderStatus.CONFIRMED, OrderStatus.PAID}
)
RESTOCKED = {
    OrderStatus.CANCELLED: (StockReason.ORDER, "Annulation de la commande {number}"),
    OrderStatus.RETURNED: (StockReason.RETURN, "Retour de la commande {number}"),
}


@dataclass(frozen=True, slots=True)
class StatusChange:
    order: Order
    previous: OrderStatus
    status: OrderStatus


@dataclass(frozen=True, slots=True)
class AssignmentChange:
    order: Order
    previous_reseller_id: int | None
    status_change: StatusChange | None


class OrderLifecycleService:
    def __init__(
        self,
        orders: OrderRepository,
        machine: OrderStateMachine,
        inventory: Inventory,
        resellers: ResellerDirectory,
    ) -> None:
        self._orders = orders
        self._machine = machine
        self._inventory = inventory
        self._resellers = resellers

    def allowed(self, order: Order, actor: Actor) -> tuple[OrderStatus, ...]:
        targets = self._machine.allowed(state_of(order), actor)
        return tuple(status for status in OrderStatus if status in targets)

    def transition(self, order: Order, actor: Actor, command: TransitionOrder) -> StatusChange:
        self._machine.ensure(state_of(order), command.to, actor)
        return self._move(order, actor, command.to, note=command.note or command.reason)

    def cancel(self, order: Order, actor: Actor, command: CancelOrder) -> StatusChange:
        self._machine.ensure(state_of(order), OrderStatus.CANCELLED, actor)
        order.cancel_reason = command.reason.value
        order.cancel_details = " ".join(command.details.split())[:500]
        self._orders.save(order, fields=("cancel_reason", "cancel_details"))
        return self._move(order, actor, OrderStatus.CANCELLED, note=order.cancel_details)

    def assign(self, order: Order, actor: Actor, command: AssignOrder) -> AssignmentChange:
        if order.order_status not in REASSIGNABLE:
            raise AssignmentClosed
        reseller = self._resellers.active(command.reseller_id)
        if reseller is None:
            raise ResellerNotFound
        previous_reseller_id = order.assigned_reseller_id
        order.assigned_reseller_id = reseller.id
        self._orders.save(order, fields=("assigned_reseller",))
        note = command.note or f"Assignée à {reseller.name}"
        if order.order_status is OrderStatus.PENDING:
            change = self._move(order, actor, OrderStatus.ASSIGNED, note=note)
            return AssignmentChange(order, previous_reseller_id, change)
        self._record(order, actor, order.order_status, order.order_status, note)
        return AssignmentChange(order, previous_reseller_id, None)

    def decline(self, order: Order, actor: Actor, command: DeclineAssignment) -> StatusChange:
        if not actor.owns(order.assigned_reseller_id):
            raise NotAssignedToYou
        if order.order_status is not OrderStatus.ASSIGNED:
            raise AssignmentClosed
        order.assigned_reseller_id = None
        self._orders.save(order, fields=("assigned_reseller",))
        return self._move(
            order, actor, OrderStatus.PENDING, note=command.reason or "Assignation déclinée"
        )

    def _move(self, order: Order, actor: Actor, status: OrderStatus, *, note: str) -> StatusChange:
        previous = order.order_status
        order.status = status.value
        self._orders.save(order, fields=("status",))
        self._record(order, actor, previous, status, note)
        if status in RESTOCKED:
            self._restock(order, actor, status)
        return StatusChange(order, previous, status)

    def _record(
        self, order: Order, actor: Actor, previous: OrderStatus, status: OrderStatus, note: str
    ) -> None:
        self._orders.record(
            order,
            previous=previous,
            status=status,
            actor_id=actor.user_id,
            actor_role=actor_role(actor),
            note=note,
        )

    def _restock(self, order: Order, actor: Actor, status: OrderStatus) -> None:
        reason, note = RESTOCKED[status]
        lines = [
            StockLine(
                product_id=item.product_id, variant_id=item.variant_id, quantity=item.quantity
            )
            for item in self._orders.items(order)
            if item.product_id is not None
        ]
        if lines:
            self._inventory.release(
                lines,
                StockSource(kind=ORDER_SOURCE, id=order.pk, actor_id=actor.user_id),
                reason=reason,
                note=note.format(number=order.number),
            )


def state_of(order: Order) -> OrderState:
    return OrderState(
        status=order.order_status,
        client_id=order.client_id,
        reseller_id=order.assigned_reseller_id,
    )

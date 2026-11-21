from apps.loyalty.facades import PointsFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderLineReturned, OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

UNDONE = frozenset({OrderStatus.CANCELLED, OrderStatus.RETURNED})


@event_bus.on(OrderStatusChanged, transactional=True)
def settle_points(event: OrderStatusChanged) -> None:
    points = container.resolve(PointsFacade)
    if event.status is OrderStatus.DELIVERED:
        points.delivered(event.order_id, event.occurred_at)
    elif event.status in UNDONE:
        points.undone(event.order_id)


@event_bus.on(OrderLineReturned, transactional=True)
def settle_points_of_returned_line(event: OrderLineReturned) -> None:
    container.resolve(PointsFacade).line_returned(event.order_id, event.amount_paid, event.points)

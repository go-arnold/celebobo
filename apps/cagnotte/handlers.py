from apps.cagnotte.facades import CagnotteFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderLineReturned, OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

UNDONE = frozenset({OrderStatus.CANCELLED, OrderStatus.RETURNED})


# delivered: the cashback or boosted points of the operation the order was placed under; a
# cancelled or returned order loses it
@event_bus.on(OrderStatusChanged, transactional=True)
def settle_reward(event: OrderStatusChanged) -> None:
    cagnotte = container.resolve(CagnotteFacade)
    if event.status is OrderStatus.DELIVERED:
        cagnotte.delivered(event.order_id, event.occurred_at)
    elif event.status in UNDONE:
        cagnotte.undone(event.order_id)


@event_bus.on(OrderLineReturned, transactional=True)
def settle_reward_of_returned_line(event: OrderLineReturned) -> None:
    container.resolve(CagnotteFacade).line_returned(event.order_id)

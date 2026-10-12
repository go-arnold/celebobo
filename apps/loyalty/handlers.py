from apps.loyalty.facades import CashbackFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

UNDONE = frozenset({OrderStatus.CANCELLED, OrderStatus.RETURNED})


@event_bus.on(OrderStatusChanged)
def settle_cashback(event: OrderStatusChanged) -> None:
    cashback = container.resolve(CashbackFacade)
    if event.status is OrderStatus.DELIVERED:
        cashback.delivered(event.order_id, event.occurred_at)
    elif event.status in UNDONE:
        cashback.undone(event.order_id)

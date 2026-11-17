from apps.loyalty.facades import CashbackFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderLineReturned, OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

UNDONE = frozenset({OrderStatus.CANCELLED, OrderStatus.RETURNED})


@event_bus.on(OrderStatusChanged, transactional=True)
def settle_cashback(event: OrderStatusChanged) -> None:
    cashback = container.resolve(CashbackFacade)
    if event.status is OrderStatus.DELIVERED:
        cashback.delivered(event.order_id, event.occurred_at)
    elif event.status in UNDONE:
        cashback.undone(event.order_id)


@event_bus.on(OrderLineReturned, transactional=True)
def settle_cashback_of_returned_line(event: OrderLineReturned) -> None:
    container.resolve(CashbackFacade).line_returned(
        event.order_id, event.amount_paid, event.cashback
    )

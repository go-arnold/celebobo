from apps.cash.facades import CashFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

# the reseller collects the money when the client pays (or at the latest on delivery)
COLLECTED = frozenset({OrderStatus.PAID, OrderStatus.DELIVERED})


@event_bus.on(OrderStatusChanged, transactional=True)
def follow_reseller_cash(event: OrderStatusChanged) -> None:
    cash = container.resolve(CashFacade)
    if event.status in COLLECTED:
        cash.order_paid(event.order_id)
    elif event.status is OrderStatus.CANCELLED:
        cash.order_cancelled(event.order_id)

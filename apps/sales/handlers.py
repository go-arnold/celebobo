from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderStatusChanged
from apps.sales.facades import SalesFacade
from core.container import container
from core.events.bus import event_bus


@event_bus.on(OrderStatusChanged)
def return_sales_of_returned_order(event: OrderStatusChanged) -> None:
    if event.status is OrderStatus.RETURNED:
        container.resolve(SalesFacade).order_returned(event.order_id)

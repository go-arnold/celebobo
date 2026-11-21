from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderLineReturned, OrderStatusChanged
from apps.sales.facades import CommissionFacade, SalesFacade
from core.container import container
from core.events.bus import event_bus


@event_bus.on(OrderStatusChanged, transactional=True)
def return_sales_of_returned_order(event: OrderStatusChanged) -> None:
    if event.status is OrderStatus.RETURNED:
        container.resolve(SalesFacade).order_returned(event.order_id)


@event_bus.on(OrderLineReturned, transactional=True)
def return_sale_of_returned_line(event: OrderLineReturned) -> None:
    container.resolve(SalesFacade).order_line_returned(event.item_id, event.quantity)


# the delivery fee goes back to the reseller who delivered; a return keeps it (the fee is not
# refunded with the products), a cancellation takes it back
@event_bus.on(OrderStatusChanged, transactional=True)
def settle_delivery_fee(event: OrderStatusChanged) -> None:
    if event.status is OrderStatus.DELIVERED:
        container.resolve(CommissionFacade).order_delivered(event.order_id, event.occurred_at)
    elif event.status is OrderStatus.CANCELLED:
        container.resolve(CommissionFacade).order_cancelled(event.order_id)

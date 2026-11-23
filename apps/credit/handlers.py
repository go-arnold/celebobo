from apps.credit.facades import StoreCreditFacade
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.events import OrderLineReturned, OrderRepriced, OrderStatusChanged
from core.container import container
from core.events.bus import event_bus

UNDONE = frozenset({OrderStatus.CANCELLED, OrderStatus.RETURNED})


@event_bus.on(OrderStatusChanged, transactional=True)
def give_credit_back(event: OrderStatusChanged) -> None:
    if event.status in UNDONE:
        container.resolve(StoreCreditFacade).order_undone(event.order_id)


@event_bus.on(OrderLineReturned, transactional=True)
def settle_credit_of_returned_line(event: OrderLineReturned) -> None:
    if event.credit <= 0 and not event.as_credit:
        return
    container.resolve(StoreCreditFacade).line_returned(
        event.client_id,
        event.order_id,
        credit=event.credit,
        paid=event.amount_paid,
        as_credit=event.as_credit,
    )


@event_bus.on(OrderRepriced, transactional=True)
def settle_credit_of_repriced_order(event: OrderRepriced) -> None:
    container.resolve(StoreCreditFacade).repriced(event.order_id, event.store_credit)

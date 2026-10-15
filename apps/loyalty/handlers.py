from apps.loyalty.domain.rules import Trigger
from apps.loyalty.facades import CashbackFacade
from apps.loyalty.services.rules import LoyaltyRuleService
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


@event_bus.on(OrderStatusChanged, background=True)
def award_purchase_points(event: OrderStatusChanged) -> None:
    if event.status is not OrderStatus.DELIVERED:
        return
    rule_service = container.resolve(LoyaltyRuleService)
    rule_service.evaluate_trigger(
        trigger=Trigger.PURCHASE_MADE,
        user_id=event.client_id,
        now=event.occurred_at,
        context={
            "user_id": event.client_id,
            "reference_type": "order",
            "reference_id": str(event.order_id),
        },
    )

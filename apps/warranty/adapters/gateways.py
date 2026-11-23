from apps.orders.domain.commands import ReturnLine
from apps.orders.domain.read_models import ClaimableLine
from apps.orders.facades import DispatchFacade
from apps.orders.selectors import ClaimableLineSelector
from core.container import container
from core.domain.actor import Actor


class OrdersLines:
    def __init__(self) -> None:
        self._selector = ClaimableLineSelector()

    def line(self, order_id: int, item_id: int) -> ClaimableLine | None:
        return self._selector.line(order_id, item_id)

    def of_order(self, order_id: int) -> tuple[ClaimableLine, ...]:
        return self._selector.of_order(order_id)


class OrdersLineRefunds:
    def refund_unit(
        self, actor: Actor, order_id: int, item_id: int, *, reason: str, as_credit: bool = False
    ) -> None:
        container.resolve(DispatchFacade).return_line(
            actor, order_id, item_id, ReturnLine(quantity=1, reason=reason, as_credit=as_credit)
        )

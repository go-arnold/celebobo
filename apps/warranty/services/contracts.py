from typing import Protocol

from apps.orders.domain.read_models import ClaimableLine
from core.domain.actor import Actor


class OrderLines(Protocol):
    def line(self, order_id: int, item_id: int) -> ClaimableLine | None: ...

    def of_order(self, order_id: int) -> tuple[ClaimableLine, ...]: ...


class LineRefunds(Protocol):
    """A refund takes the unit back through the order's line return (stock, points, refund due)."""

    def refund_unit(self, actor: Actor, order_id: int, item_id: int, *, reason: str) -> None: ...

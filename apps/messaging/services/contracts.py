from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from apps.accounts.domain.read_models import Contact
from apps.messaging.domain.notifications import RenderedNotification
from apps.orders.domain.read_models import AdjustableItem, OrderRef, QuotableOrder
from core.domain.actor import Actor


class OrderGateway(Protocol):
    def ref(self, order_id: int) -> OrderRef: ...

    def adjustable(self, actor: Actor, order_id: int, item_id: int) -> AdjustableItem: ...

    def apply_price(
        self, actor: Actor, order_id: int, item_id: int, price: Decimal
    ) -> AdjustableItem: ...

    def shipping_quotable(self, actor: Actor, order_id: int) -> QuotableOrder: ...

    def delivery_code(self, order_id: int) -> str: ...

    def accept_shipping(
        self, actor: Actor, order_id: int, fee: Decimal, delivery_estimate: str
    ) -> None: ...

    def last_orders(self, client_ids: Iterable[int]) -> dict[int, datetime]: ...


class Directory(Protocol):
    def staff_ids(self) -> list[int]: ...

    def contacts(self, user_ids: Iterable[int]) -> dict[int, Contact]: ...

    def subscribed(self, user_ids: Iterable[int], topic: str, channel: str) -> set[int]: ...

    def reseller_name(self, reseller_id: int) -> str | None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class Delivery:
    recipient_ids: tuple[int, ...]
    notification: RenderedNotification
    conversation_id: int | None = None
    order_id: int | None = None


class Notifier(Protocol):
    def deliver(self, deliveries: Sequence[Delivery]) -> None: ...

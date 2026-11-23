from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import DeliveryAddress
from apps.orders.domain.read_models import PersonBrief, SuggestedReseller
from apps.orders.models import Order
from core.domain.actor import Actor


class Inventory(Protocol):
    def price(self, lines: Sequence[StockLine], *, lock: bool = False) -> list[PricedLine]: ...

    def reserve(self, lines: Sequence[StockLine], source: StockSource) -> None: ...

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None: ...


class Wallet(Protocol):
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal: ...

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None: ...

    def earned(self, order_id: int) -> Decimal | None: ...


class CreditWallet(Protocol):
    """The client's store credit (avoir): pays products and delivery, 6 months (step 7.3)."""

    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal: ...

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None: ...


class AddressBook(Protocol):
    def snapshot(self, user_id: int, address_id: int) -> DeliveryAddress: ...

    def default_city(self, user_id: int) -> str | None: ...


class ResellerDirectory(Protocol):
    def active(self, reseller_id: int) -> PersonBrief | None: ...

    def assignable(self, search: str | None) -> list[PersonBrief]: ...

    # the active reseller who invited each client, keyed by client id
    def inviters(self, client_ids: Iterable[int]) -> dict[int, SuggestedReseller]: ...


class CashGate(Protocol):
    """Why a reseller may not get new orders for now (cash held over their cap, or not remitted
    within 24 hours), or None; for one reseller or many."""

    def blocked_reason(self, reseller_id: int) -> str | None: ...

    def blocked(self, reseller_ids: Iterable[int]) -> dict[int, str]: ...


class SuspensionGate(Protocol):
    """Until when a reseller is suspended (reseller policy, section 10), for one or many."""

    def suspended_until(self, reseller_id: int) -> datetime | None: ...

    def suspended(self, reseller_ids: Iterable[int]) -> dict[int, datetime]: ...


class OrderThreads(Protocol):
    def open_for_order(self, order: Order) -> int | None: ...

    # viewer: only a thread they may still open (a reseller loses it once closed after the order)
    def thread_for(self, order_id: int, viewer: Actor | None = None) -> int | None: ...

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import DeliveryAddress
from apps.orders.domain.read_models import PersonBrief
from apps.orders.models import Order


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


class Members(Protocol):
    def is_member(self, user_id: int) -> bool: ...


class AddressBook(Protocol):
    def snapshot(self, user_id: int, address_id: int) -> DeliveryAddress: ...

    def default_city(self, user_id: int) -> str | None: ...


class ResellerDirectory(Protocol):
    def active(self, reseller_id: int) -> PersonBrief | None: ...

    def assignable(self, search: str | None) -> list[PersonBrief]: ...


class OrderThreads(Protocol):
    def open_for_order(self, order: Order) -> int | None: ...

    def thread_for(self, order_id: int) -> int | None: ...

from collections.abc import Sequence
from typing import Protocol

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import DeliveryAddress
from apps.orders.domain.read_models import PersonBrief
from apps.orders.models import Order


class Inventory(Protocol):
    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]: ...

    def reserve(self, lines: Sequence[StockLine], source: StockSource) -> None: ...

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None: ...


class AddressBook(Protocol):
    def snapshot(self, user_id: int, address_id: int) -> DeliveryAddress: ...


class ResellerDirectory(Protocol):
    def active(self, reseller_id: int) -> PersonBrief | None: ...

    def assignable(self, search: str | None) -> list[PersonBrief]: ...


class OrderThreads(Protocol):
    def open_for_order(self, order: Order) -> int | None: ...

    def thread_for(self, order_id: int) -> int | None: ...

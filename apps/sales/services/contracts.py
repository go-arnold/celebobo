from collections.abc import Sequence
from typing import Protocol

from apps.accounts.domain.read_models import SellerProfile
from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.read_models import ConvertibleOrder
from core.domain.actor import Actor


class Inventory(Protocol):
    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]: ...

    def cost_of(self, product_id: int, variant_id: int | None) -> PricedLine | None: ...

    def reserve(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason
    ) -> None: ...

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None: ...

    def count_sales(self, product_id: int, quantity: int, *, actor_id: int | None) -> None: ...


class OrderBook(Protocol):
    def convertible(self, actor: Actor, search: str | None) -> list[ConvertibleOrder]: ...

    def order(self, actor: Actor, order_id: int) -> ConvertibleOrder: ...

    def mark_delivered(self, order_id: int, *, note: str) -> None: ...


class Sellers(Protocol):
    def profile(self, user_id: int) -> SellerProfile | None: ...

    def resellers(self) -> list[SellerProfile]: ...

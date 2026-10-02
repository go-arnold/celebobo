from collections.abc import Sequence
from typing import Protocol

from apps.catalog.domain.read_models import ProductLabel
from apps.orders.domain.read_models import OrderSummary
from apps.sales.domain.read_models import SaleView
from core.domain.actor import Actor


class CatalogLabels(Protocol):
    def products(self, ids: Sequence[int]) -> dict[int, ProductLabel]: ...

    def categories(self, ids: Sequence[int]) -> dict[int, str]: ...

    def stocked(self, *, limit: int) -> list[ProductLabel]: ...


class SellerNames(Protocol):
    def names(self, ids: Sequence[int]) -> dict[int, str]: ...


class OrderPipeline(Protocol):
    def open_orders(self, actor: Actor, *, limit: int) -> tuple[list[OrderSummary], int]: ...


class SalesFeed(Protocol):
    def recent(self, actor: Actor, *, limit: int) -> list[SaleView]: ...

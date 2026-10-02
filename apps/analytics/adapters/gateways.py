from collections.abc import Sequence

from apps.accounts.selectors import SellerSelector
from apps.catalog.domain.read_models import ProductLabel
from apps.catalog.selectors import ProductLabelSelector
from apps.orders.domain.read_models import OrderSummary
from apps.orders.selectors import OrderSelector
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.read_models import SaleView
from apps.sales.selectors import SaleSelector
from core.domain.actor import Actor


class CatalogProductLabels:
    def __init__(self) -> None:
        self._selector = ProductLabelSelector()

    def products(self, ids: Sequence[int]) -> dict[int, ProductLabel]:
        return self._selector.products(ids)

    def categories(self, ids: Sequence[int]) -> dict[int, str]:
        return self._selector.categories(ids)

    def stocked(self, *, limit: int) -> list[ProductLabel]:
        return self._selector.stocked(limit=limit)


class AccountsSellerNames:
    def names(self, ids: Sequence[int]) -> dict[int, str]:
        return SellerSelector().names(ids)


class OrdersPipeline:
    def open_orders(self, actor: Actor, *, limit: int) -> tuple[list[OrderSummary], int]:
        return OrderSelector().open_page(actor, limit=limit)


class SalesRecentFeed:
    def recent(self, actor: Actor, *, limit: int) -> list[SaleView]:
        sales, _, _ = SaleSelector().page(actor, SaleFilters(), offset=0, limit=limit)
        return sales

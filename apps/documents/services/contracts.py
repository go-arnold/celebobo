from collections.abc import Iterator, Mapping
from typing import Any, Protocol

from apps.analytics.domain.queries import AnalyticsFilters
from apps.analytics.domain.read_models import (
    CategoryPerformance,
    ProductPerformance,
    SellerRanking,
    Summary,
)
from apps.catalog.domain.backoffice import AdminProductRow
from apps.catalog.domain.management import ProductChanges, ProductDraft
from apps.documents.domain.tables import Table
from apps.orders.domain.read_models import OrderDetail
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.read_models import SaleView
from core.domain.actor import Actor


class TabularWriter(Protocol):
    extension: str
    content_type: str

    def write(self, table: Table) -> bytes: ...


class PdfRenderer(Protocol):
    def render(self, template: str, context: Mapping[str, Any]) -> bytes: ...


class FileStore(Protocol):
    def save(self, name: str, content: bytes) -> str: ...

    def read(self, path: str) -> bytes: ...

    def delete(self, path: str) -> None: ...


class SalesSource(Protocol):
    def sales(self, actor: Actor, filters: SaleFilters, *, limit: int) -> Iterator[SaleView]: ...


class ProductSource(Protocol):
    def products(self, *, limit: int) -> Iterator[AdminProductRow]: ...


class ProductCatalog(Protocol):
    def category_ids(self) -> dict[str, int]: ...

    def product_id(self, slug: str) -> int | None: ...

    def create(self, actor: Actor, draft: ProductDraft) -> int: ...

    def update(self, actor: Actor, product_id: int, changes: ProductChanges) -> None: ...

    def set_stock(self, actor: Actor, product_id: int, stock: int) -> None: ...


class AnalyticsSource(Protocol):
    def summary(self, actor: Actor, filters: AnalyticsFilters) -> Summary: ...

    def categories(self, actor: Actor, filters: AnalyticsFilters) -> list[CategoryPerformance]: ...

    def top_products(self, actor: Actor, filters: AnalyticsFilters) -> list[ProductPerformance]: ...

    def sellers(self, actor: Actor, filters: AnalyticsFilters) -> list[SellerRanking]: ...


class OrderSource(Protocol):
    def for_client(self, client_id: int, number: str) -> OrderDetail: ...

    def for_backoffice(self, actor: Actor, order_id: int) -> OrderDetail: ...

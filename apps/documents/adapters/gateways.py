from collections.abc import Iterator

from apps.analytics.domain.queries import AnalyticsFilters
from apps.analytics.domain.read_models import (
    CategoryPerformance,
    ProductPerformance,
    SellerRanking,
    Summary,
)
from apps.analytics.facades import AnalyticsFacade
from apps.catalog.domain.backoffice import AdminProductRow
from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.management import (
    AdjustmentMode,
    BackofficeProductFilters,
    ProductChanges,
    ProductDraft,
    ProductStatus,
    StockAdjustment,
)
from apps.catalog.facades import ProductAdminFacade
from apps.catalog.selectors import AdminCategorySelector, AdminProductSelector, ProductLabelSelector
from apps.orders.domain.read_models import OrderDetail
from apps.orders.selectors import OrderSelector
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.read_models import SaleView
from apps.sales.selectors import SaleSelector
from core.container import container
from core.domain.actor import Actor

BATCH = 500


class SalesLedgerSource:
    def sales(self, actor: Actor, filters: SaleFilters, *, limit: int) -> Iterator[SaleView]:
        selector = SaleSelector()
        offset = 0
        while offset < limit:
            sales, total, _ = selector.page(
                actor, filters, offset=offset, limit=min(BATCH, limit - offset)
            )
            yield from sales
            offset += BATCH
            if offset >= total:
                return


class CatalogProductSource:
    def products(self, *, limit: int) -> Iterator[AdminProductRow]:
        selector = AdminProductSelector()
        filters = BackofficeProductFilters(status=ProductStatus.ALL)
        offset = 0
        while offset < limit:
            rows, total, _ = selector.page(filters, offset=offset, limit=min(BATCH, limit - offset))
            yield from rows
            offset += BATCH
            if offset >= total:
                return


class CatalogProductWriter:
    def category_ids(self) -> dict[str, int]:
        return {category.slug: category.id for category in AdminCategorySelector().all()}

    def product_id(self, slug: str) -> int | None:
        return ProductLabelSelector().id_for_slug(slug)

    def create(self, actor: Actor, draft: ProductDraft) -> int:
        return container.resolve(ProductAdminFacade).create(actor, draft).row.id

    def update(self, actor: Actor, product_id: int, changes: ProductChanges) -> None:
        container.resolve(ProductAdminFacade).update(actor, product_id, changes)

    def set_stock(self, actor: Actor, product_id: int, stock: int) -> None:
        container.resolve(ProductAdminFacade).adjust_stock(
            actor,
            product_id,
            StockAdjustment(
                mode=AdjustmentMode.SET,
                value=stock,
                reason=StockReason.INVENTORY,
                note="Import CSV",
            ),
        )


class AnalyticsInsights:
    def summary(self, actor: Actor, filters: AnalyticsFilters) -> Summary:
        return container.resolve(AnalyticsFacade).summary(actor, filters)

    def categories(self, actor: Actor, filters: AnalyticsFilters) -> list[CategoryPerformance]:
        return container.resolve(AnalyticsFacade).categories(actor, filters)

    def top_products(self, actor: Actor, filters: AnalyticsFilters) -> list[ProductPerformance]:
        return container.resolve(AnalyticsFacade).top_products(actor, filters, limit=10)

    def sellers(self, actor: Actor, filters: AnalyticsFilters) -> list[SellerRanking]:
        return container.resolve(AnalyticsFacade).sellers(actor, filters)


class OrdersInvoiceSource:
    def for_client(self, client_id: int, number: str) -> OrderDetail:
        return OrderSelector().client_detail(client_id, number)

    def for_backoffice(self, actor: Actor, order_id: int) -> OrderDetail:
        return OrderSelector().backoffice_detail(actor, order_id)

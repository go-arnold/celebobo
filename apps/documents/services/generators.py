from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from django.utils import timezone

from apps.analytics.domain.periods import Period
from apps.analytics.domain.queries import AnalyticsFilters
from apps.documents.domain.enums import JobFormat
from apps.documents.domain.tables import Column, RenderedFile, Table
from apps.documents.services.contracts import (
    AnalyticsSource,
    PdfRenderer,
    ProductSource,
    SalesSource,
)
from apps.documents.services.writers import writer_registry
from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.commands import SaleFilters
from apps.sales.domain.enums import SalesPeriod, SaleStatus
from core.domain.actor import Actor
from core.registry import Registry


@dataclass(frozen=True, slots=True)
class JobRequest:
    actor: Actor
    format: JobFormat
    params: dict[str, Any]
    upload: bytes | None = None


@dataclass(slots=True)
class JobOutput:
    file: RenderedFile | None
    summary: dict[str, Any] = field(default_factory=dict)


class JobGenerator(Protocol):
    def run(self, request: JobRequest) -> JobOutput: ...


generator_registry: Registry[JobGenerator] = Registry("document job")

SALE_COLUMNS = (
    Column("sold_at", "Date"),
    Column("product", "Produit"),
    Column("variant", "Variante"),
    Column("quantity", "Qté", numeric=True),
    Column("unit_price", "Prix unitaire", numeric=True),
    Column("total", "Total", numeric=True),
    Column("refunded", "Remboursé", numeric=True),
    Column("profit", "Marge", numeric=True),
    Column("payment", "Paiement"),
    Column("status", "Statut"),
    Column("seller", "Vendeur"),
    Column("customer", "Client"),
    Column("order", "Commande"),
)
PRODUCT_COLUMNS = (
    Column("slug", "slug"),
    Column("name", "name"),
    Column("category", "category"),
    Column("price", "price", numeric=True),
    Column("sale_price", "sale_price", numeric=True),
    Column("cost_price", "cost_price", numeric=True),
    Column("stock", "stock", numeric=True),
    Column("stock_threshold", "stock_threshold", numeric=True),
    Column("is_active", "is_active"),
    Column("sales_count", "sales_count", numeric=True),
)


def stamp() -> str:
    return timezone.localtime().strftime("%Y%m%d-%H%M")


def tabular(table: Table, request: JobRequest, basename: str) -> RenderedFile:
    writer = writer_registry.create(request.format.value)
    return RenderedFile(
        content=writer.write(table),
        filename=f"{basename}-{stamp()}.{writer.extension}",
        content_type=writer.content_type,
    )


class SalesExport:
    def __init__(self, source: SalesSource, *, limit: int) -> None:
        self._source = source
        self._limit = limit

    def run(self, request: JobRequest) -> JobOutput:
        sales = list(
            self._source.sales(request.actor, sale_filters(request.params), limit=self._limit)
        )
        revenue = sum((sale.total - sale.refunded_amount for sale in sales), Decimal(0))
        table = Table(
            title="Ventes",
            subtitle=f"{len(sales)} ventes",
            columns=SALE_COLUMNS,
            rows=[
                (
                    sale.sold_at,
                    sale.product_name,
                    sale.variant_label,
                    sale.quantity,
                    sale.unit_price,
                    sale.total,
                    sale.refunded_amount,
                    sale.profit,
                    sale.payment_method.value,
                    sale.status.value,
                    sale.seller.name,
                    sale.sold_to or (sale.buyer.name if sale.buyer else ""),
                    sale.order_number or "",
                )
                for sale in sales
            ],
            totals=(("Chiffre d'affaires net", f"{revenue:.2f}"),),
        )
        return JobOutput(tabular(table, request, "ventes"), {"rows": len(sales)})


class ProductsExport:
    def __init__(self, source: ProductSource, *, limit: int) -> None:
        self._source = source
        self._limit = limit

    def run(self, request: JobRequest) -> JobOutput:
        products = list(self._source.products(limit=self._limit))
        table = Table(
            title="Produits",
            columns=PRODUCT_COLUMNS,
            rows=[
                (
                    product.slug,
                    product.name,
                    product.category.slug,
                    product.price,
                    product.sale_price,
                    product.cost_price,
                    product.stock,
                    product.stock_threshold,
                    "1" if product.status.value == "active" else "0",
                    product.sales_count,
                )
                for product in products
            ],
        )
        return JobOutput(tabular(table, request, "produits"), {"rows": len(products)})


class AnalyticsReport:
    def __init__(
        self, source: AnalyticsSource, renderer: PdfRenderer, branding: dict[str, str]
    ) -> None:
        self._source = source
        self._renderer = renderer
        self._branding = branding

    def run(self, request: JobRequest) -> JobOutput:
        filters = analytics_filters(request.params)
        actor = request.actor
        summary = self._source.summary(actor, filters)
        content = self._renderer.render(
            "documents/analytics_report.html",
            {
                "summary": summary,
                "categories": self._source.categories(actor, filters),
                "products": self._source.top_products(actor, filters),
                "sellers": self._source.sellers(actor, filters) if actor.is_staff else [],
                "generated_at": timezone.localtime(),
                **self._branding,
            },
        )
        return JobOutput(
            RenderedFile(
                content=content,
                filename=f"rapport-{stamp()}.pdf",
                content_type="application/pdf",
            ),
            {"revenue": str(summary.revenue.value)},
        )


def sale_filters(params: dict[str, Any]) -> SaleFilters:
    return SaleFilters(
        period=SalesPeriod(params["period"]) if params.get("period") else None,
        date_from=_date(params.get("date_from")),
        date_to=_date(params.get("date_to")),
        payment_method=PaymentMethod(params["payment_method"])
        if params.get("payment_method")
        else None,
        seller_id=params.get("seller_id"),
        product_id=params.get("product_id"),
        status=SaleStatus(params["status"]) if params.get("status") else None,
        search=params.get("search") or None,
    )


def analytics_filters(params: dict[str, Any]) -> AnalyticsFilters:
    return AnalyticsFilters(
        period=Period(params["period"]) if params.get("period") else None,
        date_from=_date(params.get("date_from")),
        date_to=_date(params.get("date_to")),
        category_id=params.get("category_id"),
        payment_method=PaymentMethod(params["payment_method"])
        if params.get("payment_method")
        else None,
        seller_id=params.get("seller_id"),
    )


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None

from django.utils import timezone

from apps.documents.adapters.gateways import (
    AnalyticsInsights,
    CatalogProductSource,
    CatalogProductWriter,
    OrdersInvoiceSource,
    SalesLedgerSource,
)
from apps.documents.adapters.rendering import DjangoFileStore, WeasyPdfRenderer
from apps.documents.conf import DocumentSettings, document_settings
from apps.documents.domain.enums import JobFormat, JobKind
from apps.documents.facades import DocumentJobFacade, InvoiceFacade
from apps.documents.repositories import JobRepository
from apps.documents.selectors import JobSelector
from apps.documents.services.contracts import (
    AnalyticsSource,
    FileStore,
    OrderSource,
    PdfRenderer,
    ProductCatalog,
    ProductSource,
    SalesSource,
)
from apps.documents.services.generators import (
    AnalyticsReport,
    ProductsExport,
    SalesExport,
    generator_registry,
)
from apps.documents.services.importer import ProductImport
from apps.documents.services.invoices import InvoiceBuilder
from apps.documents.services.jobs import JobService
from apps.documents.services.writers import (
    CsvWriter,
    PdfTableWriter,
    XlsxWriter,
    writer_registry,
)
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def branding(settings: DocumentSettings) -> dict[str, str]:
    return {
        "company_name": settings.company_name,
        "company_address": settings.company_address,
        "company_contact": settings.company_contact,
    }


def register(container: Container) -> None:
    container.register(PdfRenderer, lambda _: WeasyPdfRenderer())
    container.register(FileStore, lambda _: DjangoFileStore())
    container.register(SalesSource, lambda _: SalesLedgerSource())
    container.register(ProductSource, lambda _: CatalogProductSource())
    container.register(ProductCatalog, lambda _: CatalogProductWriter())
    container.register(AnalyticsSource, lambda _: AnalyticsInsights())
    container.register(OrderSource, lambda _: OrdersInvoiceSource())
    container.register(DocumentJobFacade, _job_facade, lifetime=Lifetime.TRANSIENT)
    container.register(InvoiceFacade, _invoice_facade, lifetime=Lifetime.TRANSIENT)
    register_writers(container)
    register_generators(container)


def register_writers(container: Container) -> None:
    writer_registry.add(JobFormat.CSV.value, CsvWriter, replace=True)
    writer_registry.add(JobFormat.XLSX.value, XlsxWriter, replace=True)
    writer_registry.add(
        JobFormat.PDF.value,
        lambda: PdfTableWriter(container.resolve(PdfRenderer), branding(document_settings())),
        replace=True,
    )


def register_generators(container: Container) -> None:
    settings = document_settings
    generator_registry.add(
        JobKind.SALES_EXPORT.value,
        lambda: SalesExport(container.resolve(SalesSource), limit=settings().max_export_rows),
        replace=True,
    )
    generator_registry.add(
        JobKind.PRODUCTS_EXPORT.value,
        lambda: ProductsExport(container.resolve(ProductSource), limit=settings().max_export_rows),
        replace=True,
    )
    generator_registry.add(
        JobKind.PRODUCTS_IMPORT.value,
        lambda: ProductImport(
            container.resolve(ProductCatalog),
            max_rows=settings().max_import_rows,
            max_bytes=settings().max_import_bytes,
        ),
        replace=True,
    )
    generator_registry.add(
        JobKind.ANALYTICS_REPORT.value,
        lambda: AnalyticsReport(
            container.resolve(AnalyticsSource),
            container.resolve(PdfRenderer),
            branding(settings()),
        ),
        replace=True,
    )


def _job_facade(container: Container) -> DocumentJobFacade:
    settings = document_settings()
    return DocumentJobFacade(
        jobs=JobService(JobRepository(), container.resolve(FileStore), clock=timezone.now),
        selector=JobSelector(),
        publisher=container.resolve(EventPublisher),
        max_import_rows=settings.max_import_rows,
        max_import_bytes=settings.max_import_bytes,
        retention_days=settings.retention_days,
    )


def _invoice_facade(container: Container) -> InvoiceFacade:
    return InvoiceFacade(
        orders=container.resolve(OrderSource),
        builder=InvoiceBuilder(container.resolve(PdfRenderer), branding(document_settings())),
    )

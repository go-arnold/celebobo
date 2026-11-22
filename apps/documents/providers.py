from datetime import timedelta

from django.conf import settings as django_settings
from django.utils import timezone

from apps.documents.adapters.gateways import (
    AnalyticsInsights,
    CatalogProductSource,
    CatalogProductWriter,
    EmailReceiptMailer,
    LoyaltyPointsStatements,
    OrdersInvoiceSource,
    SalesLedgerSource,
)
from apps.documents.adapters.personal_data import (
    AccountCollector,
    ConsentsCollector,
    FavoritesCollector,
    MessagesCollector,
    OrdersCollector,
    PointsCollector,
    PreferencesCollector,
    ResellerApplicationsCollector,
    ResellerCollector,
    ReviewsCollector,
)
from apps.documents.adapters.qr import SvgQrCode
from apps.documents.adapters.rendering import DjangoFileStore, WeasyPdfRenderer
from apps.documents.conf import DocumentSettings, document_settings
from apps.documents.domain.enums import JobFormat, JobKind
from apps.documents.facades import (
    DocumentJobFacade,
    InvoiceFacade,
    PersonalDataFacade,
    ReceiptFacade,
)
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
from apps.documents.services.jobs import JobService, PersonalDataPolicy
from apps.documents.services.personal_data import PersonalDataExport, collector_registry
from apps.documents.services.receipts import ReceiptService
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
        "privacy_contact": settings.privacy_contact,
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
    container.register(ReceiptFacade, _receipt_facade, lifetime=Lifetime.TRANSIENT)
    container.register(PersonalDataFacade, _personal_data_facade, lifetime=Lifetime.TRANSIENT)
    register_writers(container)
    register_collectors()
    register_generators(container)


def register_writers(container: Container) -> None:
    writer_registry.add(JobFormat.CSV.value, CsvWriter, replace=True)
    writer_registry.add(JobFormat.XLSX.value, XlsxWriter, replace=True)
    writer_registry.add(
        JobFormat.PDF.value,
        lambda: PdfTableWriter(container.resolve(PdfRenderer), branding(document_settings())),
        replace=True,
    )


# one collector per app; consent records (step 6.1) join under the "consents" key
def register_collectors() -> None:
    settings = document_settings
    collector_registry.add("account", AccountCollector, replace=True)
    collector_registry.add("notification_preferences", PreferencesCollector, replace=True)
    collector_registry.add("consents", ConsentsCollector, replace=True)
    collector_registry.add(
        "orders",
        lambda: OrdersCollector(limit=settings().personal_data_max_orders),
        replace=True,
    )
    collector_registry.add("points", PointsCollector, replace=True)
    collector_registry.add("reviews", ReviewsCollector, replace=True)
    collector_registry.add("favorites", FavoritesCollector, replace=True)
    collector_registry.add(
        "messages",
        lambda: MessagesCollector(limit=settings().personal_data_max_messages),
        replace=True,
    )
    collector_registry.add("reseller_applications", ResellerApplicationsCollector, replace=True)
    collector_registry.add("reseller", ResellerCollector, replace=True)


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
    generator_registry.add(
        JobKind.PERSONAL_DATA.value,
        lambda: PersonalDataExport(collector_registry, branding(settings()), clock=timezone.now),
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
        personal_data_ttl=timedelta(hours=settings.personal_data_link_hours),
    )


def _personal_data_facade(container: Container) -> PersonalDataFacade:
    settings = document_settings()
    return PersonalDataFacade(
        jobs=JobService(JobRepository(), container.resolve(FileStore), clock=timezone.now),
        publisher=container.resolve(EventPublisher),
        policy=PersonalDataPolicy(
            cooldown=timedelta(minutes=settings.personal_data_cooldown_minutes),
            failure_cooldown=timedelta(minutes=settings.personal_data_failure_cooldown_minutes),
            stale_after=timedelta(minutes=settings.personal_data_stale_minutes),
        ),
        link_ttl=timedelta(hours=settings.personal_data_link_hours),
    )


def _receipt_facade(container: Container) -> ReceiptFacade:
    return ReceiptFacade(
        orders=container.resolve(OrderSource),
        receipts=ReceiptService(
            container.resolve(PdfRenderer),
            branding(document_settings()),
            clock=timezone.now,
            verify_page=f"{str(django_settings.FRONTEND_URL).rstrip('/')}/verifier-recu",
            qr=SvgQrCode(),
        ),
        mailer=EmailReceiptMailer(),
    )


def _invoice_facade(container: Container) -> InvoiceFacade:
    return InvoiceFacade(
        orders=container.resolve(OrderSource),
        builder=InvoiceBuilder(
            container.resolve(PdfRenderer),
            branding(document_settings()),
            LoyaltyPointsStatements(),
        ),
    )

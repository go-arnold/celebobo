from enum import StrEnum


class JobKind(StrEnum):
    SALES_EXPORT = "sales_export"
    PRODUCTS_EXPORT = "products_export"
    PRODUCTS_IMPORT = "products_import"
    ANALYTICS_REPORT = "analytics_report"


class JobFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


ALLOWED_FORMATS = {
    JobKind.SALES_EXPORT: frozenset({JobFormat.CSV, JobFormat.XLSX, JobFormat.PDF}),
    JobKind.PRODUCTS_EXPORT: frozenset({JobFormat.CSV, JobFormat.XLSX}),
    JobKind.PRODUCTS_IMPORT: frozenset({JobFormat.CSV}),
    JobKind.ANALYTICS_REPORT: frozenset({JobFormat.PDF}),
}

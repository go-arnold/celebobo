from enum import StrEnum


class JobKind(StrEnum):
    SALES_EXPORT = "sales_export"
    PRODUCTS_EXPORT = "products_export"
    PRODUCTS_IMPORT = "products_import"
    ANALYTICS_REPORT = "analytics_report"
    # "Télécharger mes données" (privacy policy, art. 211): a ZIP of everything about the owner
    PERSONAL_DATA = "personal_data"


class JobFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"
    ZIP = "zip"


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
    JobKind.PERSONAL_DATA: frozenset({JobFormat.ZIP}),
}

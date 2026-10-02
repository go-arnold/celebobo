from core.authz.catalog import permission_catalog
from core.domain.actor import Role

INVOICES_VIEW_OWN = "invoices.view.own"
INVOICES_VIEW = "invoices.view"
JOBS_VIEW_OWN = "jobs.view.own"
EXPORTS_SALES = "exports.sales"
REPORTS_ANALYTICS = "reports.analytics"
EXPORTS_PRODUCTS = "exports.products"
IMPORTS_PRODUCTS = "imports.products"

permission_catalog.grant(Role.CLIENT, INVOICES_VIEW_OWN)
permission_catalog.grant(
    Role.RESELLER, INVOICES_VIEW, JOBS_VIEW_OWN, EXPORTS_SALES, REPORTS_ANALYTICS
)
permission_catalog.grant(Role.MANAGER, EXPORTS_PRODUCTS, IMPORTS_PRODUCTS)

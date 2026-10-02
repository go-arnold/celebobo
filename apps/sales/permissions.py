from core.authz.catalog import permission_catalog
from core.domain.actor import Role

SALES_VIEW_OWN = "sales.view.own"
SALES_CREATE = "sales.create"
SALES_CONVERT = "sales.convert"
SALES_EDIT_OWN = "sales.edit.own"
COMMISSIONS_VIEW_OWN = "commissions.view.own"
SALES_VIEW_ALL = "sales.view.all"
SALES_EDIT_ALL = "sales.edit.all"
SALES_REFUND = "sales.refund"
COMMISSIONS_VIEW_ALL = "commissions.view.all"
SALES_DELETE = "sales.delete"
COMMISSIONS_PAY = "commissions.pay"

permission_catalog.grant(
    Role.RESELLER,
    SALES_VIEW_OWN,
    SALES_CREATE,
    SALES_CONVERT,
    SALES_EDIT_OWN,
    COMMISSIONS_VIEW_OWN,
)
permission_catalog.grant(
    Role.MANAGER, SALES_VIEW_ALL, SALES_EDIT_ALL, SALES_REFUND, COMMISSIONS_VIEW_ALL
)
permission_catalog.grant(Role.ADMIN, SALES_DELETE, COMMISSIONS_PAY)

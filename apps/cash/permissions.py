from core.authz.catalog import permission_catalog
from core.domain.actor import Role

# a reseller sees the cash they hold; managers (and admins) record what resellers remit
CASH_VIEW_OWN = "cash.view.own"
CASH_MANAGE = "cash.manage"

permission_catalog.grant(Role.RESELLER, CASH_VIEW_OWN)
permission_catalog.grant(Role.MANAGER, CASH_MANAGE)

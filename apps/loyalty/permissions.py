from core.authz.catalog import permission_catalog
from core.domain.actor import Role

LOYALTY_MANAGE = "loyalty.manage"

permission_catalog.grant(Role.ADMIN, LOYALTY_MANAGE)

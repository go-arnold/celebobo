from core.authz.catalog import permission_catalog
from core.domain.actor import Role

LOYALTY_MANAGE = "loyalty.manage"
POINTS_VIEW = "points.view"

permission_catalog.grant(Role.CLIENT, POINTS_VIEW)
permission_catalog.grant(Role.RESELLER, POINTS_VIEW)
permission_catalog.grant(Role.MANAGER, POINTS_VIEW)
permission_catalog.grant(Role.ADMIN, LOYALTY_MANAGE)

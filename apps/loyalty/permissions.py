from core.authz.catalog import permission_catalog
from core.domain.actor import Role

MEMBERSHIP_SUBSCRIBE = "membership.subscribe"
MEMBERSHIP_MANAGE = "membership.manage"
LOYALTY_MANAGE = "loyalty.manage"

permission_catalog.grant(Role.CLIENT, MEMBERSHIP_SUBSCRIBE)
permission_catalog.grant(Role.MANAGER, MEMBERSHIP_MANAGE)
permission_catalog.grant(Role.ADMIN, LOYALTY_MANAGE)

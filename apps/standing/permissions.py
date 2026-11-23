from core.authz.catalog import permission_catalog
from core.domain.actor import Role

# a reseller sees their level and sanctions and may explain; managers review and sanction
STANDING_VIEW_OWN = "standing.view.own"
STANDING_MANAGE = "standing.manage"

permission_catalog.grant(Role.RESELLER, STANDING_VIEW_OWN)
permission_catalog.grant(Role.MANAGER, STANDING_MANAGE)

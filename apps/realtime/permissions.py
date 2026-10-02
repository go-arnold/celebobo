from core.authz.catalog import permission_catalog
from core.domain.actor import Role

PRESENCE_VIEW = "presence.view"

permission_catalog.grant(Role.MANAGER, PRESENCE_VIEW)

from core.authz.catalog import permission_catalog
from core.domain.actor import Role

AUDIT_VIEW = "audit.view"

permission_catalog.grant(Role.ADMIN, AUDIT_VIEW)

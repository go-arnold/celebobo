from core.authz.catalog import permission_catalog
from core.domain.actor import Role

DASHBOARD_VIEW = "dashboard.view"
ANALYTICS_VIEW = "analytics.view"

permission_catalog.grant(Role.RESELLER, DASHBOARD_VIEW)
permission_catalog.grant(Role.MANAGER, ANALYTICS_VIEW)

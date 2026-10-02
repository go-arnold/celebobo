from core.authz.catalog import permission_catalog
from core.domain.actor import Role

ACCOUNT_VIEW = "account.view"
ACCOUNT_UPDATE = "account.update"
ACCOUNT_DELETE = "account.delete"
ADDRESSES_MANAGE = "addresses.manage"
PREFERENCES_MANAGE = "preferences.manage"
REALTIME_CONNECT = "realtime.connect"
AVAILABILITY_UPDATE = "availability.update"
USERS_VIEW = "users.view"
USERS_MANAGE = "users.manage"

permission_catalog.grant(
    Role.CLIENT,
    ACCOUNT_VIEW,
    ACCOUNT_UPDATE,
    ACCOUNT_DELETE,
    ADDRESSES_MANAGE,
    PREFERENCES_MANAGE,
    REALTIME_CONNECT,
)
permission_catalog.grant(Role.RESELLER, AVAILABILITY_UPDATE)
permission_catalog.grant(Role.MANAGER, USERS_VIEW)
permission_catalog.grant(Role.ADMIN, USERS_MANAGE)

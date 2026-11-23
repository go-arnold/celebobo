from core.authz.catalog import permission_catalog
from core.domain.actor import Role

# a client (and every role above, who also shop) sees their own store credit
STORE_CREDIT_VIEW_OWN = "store_credit.view.own"

permission_catalog.grant(Role.CLIENT, STORE_CREDIT_VIEW_OWN)

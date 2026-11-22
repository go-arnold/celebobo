from core.authz.catalog import permission_catalog
from core.domain.actor import Role

# a client claims for their own orders; managers (and admins) handle the claims
CLAIMS_SUBMIT_OWN = "claims.submit.own"
CLAIMS_MANAGE = "claims.manage"

permission_catalog.grant(Role.CLIENT, CLAIMS_SUBMIT_OWN)
permission_catalog.grant(Role.MANAGER, CLAIMS_MANAGE)

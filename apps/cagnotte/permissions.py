from core.authz.catalog import permission_catalog
from core.domain.actor import Role

# a client sees their Cagnotte advantages; managers send the Mobile Money cashbacks; admins set up
# the operations
CAGNOTTE_VIEW_OWN = "cagnotte.view.own"
CAGNOTTE_PAY = "cagnotte.pay"
CAGNOTTE_MANAGE = "cagnotte.manage"

permission_catalog.grant(Role.CLIENT, CAGNOTTE_VIEW_OWN)
permission_catalog.grant(Role.MANAGER, CAGNOTTE_PAY)
permission_catalog.grant(Role.ADMIN, CAGNOTTE_MANAGE)

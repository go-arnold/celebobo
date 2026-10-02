from core.authz.catalog import permission_catalog
from core.domain.actor import Role

PUSH_DEVICES = "push.devices"

permission_catalog.grant(Role.CLIENT, PUSH_DEVICES)

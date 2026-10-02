from core.authz.catalog import permission_catalog
from core.domain.actor import Role

MEDIA_UPLOAD = "media.upload"

permission_catalog.grant(Role.CLIENT, MEDIA_UPLOAD)

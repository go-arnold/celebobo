import time

from apps.media.adapters import cloudinary
from apps.media.conf import media_settings
from apps.media.facades import MediaFacade
from apps.media.repositories import MediaRepository
from apps.media.services.contracts import MediaStorage
from apps.media.services.uploads import UploadService, storage_registry
from core.authz.catalog import permission_catalog
from core.container import Container, Lifetime

ADAPTER_MODULES = (cloudinary,)


def register(container: Container) -> None:
    container.register(MediaStorage, lambda _: storage_registry.create(media_settings().storage))
    container.register(MediaFacade, _media_facade, lifetime=Lifetime.TRANSIENT)


def _media_facade(container: Container) -> MediaFacade:
    return MediaFacade(
        uploads=UploadService(
            container.resolve(MediaStorage), MediaRepository(), clock=time.time
        ),
        permissions=permission_catalog,
    )

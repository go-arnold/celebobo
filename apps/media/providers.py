import time
from datetime import timedelta

from django.utils import timezone

from apps.media.adapters import cloudinary
from apps.media.conf import media_settings
from apps.media.facades import MediaFacade, MediaMaintenanceFacade
from apps.media.repositories import MediaRepository
from apps.media.services.cleanup import OrphanSweeper
from apps.media.services.contracts import MediaStorage
from apps.media.services.uploads import UploadService, storage_registry
from core.authz.catalog import permission_catalog
from core.container import Container, Lifetime

ADAPTER_MODULES = (cloudinary,)
ORPHAN_GRACE = timedelta(hours=24)
SWEEP_BATCH = 200


def register(container: Container) -> None:
    container.register(MediaStorage, lambda _: storage_registry.create(media_settings().storage))
    container.register(MediaFacade, _media_facade, lifetime=Lifetime.TRANSIENT)
    container.register(MediaMaintenanceFacade, _maintenance_facade, lifetime=Lifetime.TRANSIENT)


def _media_facade(container: Container) -> MediaFacade:
    return MediaFacade(
        uploads=UploadService(container.resolve(MediaStorage), MediaRepository(), clock=time.time),
        permissions=permission_catalog,
    )


def _maintenance_facade(container: Container) -> MediaMaintenanceFacade:
    return MediaMaintenanceFacade(
        sweeper=OrphanSweeper(
            MediaRepository(),
            container.resolve(MediaStorage),
            grace=ORPHAN_GRACE,
            batch=SWEEP_BATCH,
            clock=timezone.now,
        )
    )

from collections.abc import Callable

from apps.media.domain.errors import InvalidUpload, UnsupportedFormat, UploadTooLarge
from apps.media.domain.policies import UploadPolicy
from apps.media.domain.uploads import CompletedUpload, UploadSignature
from apps.media.models import UploadedMedia
from apps.media.repositories import MediaRepository
from apps.media.services.contracts import MediaStorage
from core.registry import Registry

storage_registry: Registry[MediaStorage] = Registry("media storage")


class UploadService:
    def __init__(
        self, storage: MediaStorage, media: MediaRepository, *, clock: Callable[[], float]
    ) -> None:
        self._storage = storage
        self._media = media
        self._clock = clock

    def sign(self, policy: UploadPolicy) -> UploadSignature:
        return self._storage.sign_upload(policy, timestamp=int(self._clock()))

    def complete(
        self, owner_id: int, policy: UploadPolicy, upload: CompletedUpload
    ) -> UploadedMedia:
        if not upload.public_id.startswith(f"{self._storage.folder_for(policy)}/"):
            raise InvalidUpload
        if not self._storage.verify(upload):
            raise InvalidUpload
        if upload.format.lower() not in policy.formats:
            raise UnsupportedFormat
        if upload.bytes > policy.max_bytes:
            raise UploadTooLarge(meta={"max_bytes": policy.max_bytes})
        media = self._media.claim(
            upload.public_id,
            {
                "owner_id": owner_id,
                "purpose": policy.purpose.value,
                "url": self._storage.delivery_url(upload),
                "format": upload.format.lower(),
                "bytes": upload.bytes,
                "width": upload.width,
                "height": upload.height,
            },
        )
        if media.owner_id != owner_id or media.purpose != policy.purpose.value:
            raise InvalidUpload
        return media

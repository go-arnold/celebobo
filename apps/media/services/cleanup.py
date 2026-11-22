from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.media.domain.policies import UploadPurpose
from apps.media.repositories import MediaRepository
from apps.media.services.contracts import MediaStorage
from apps.media.services.references import referenced

# uploads that are about the client rather than the shop
PERSONAL = (UploadPurpose.AVATAR, UploadPurpose.MESSAGE_ATTACHMENT)


@dataclass(frozen=True, slots=True)
class SweepResult:
    checked: int
    deleted: int


class OrphanSweeper:
    def __init__(
        self,
        media: MediaRepository,
        storage: MediaStorage,
        *,
        grace: timedelta,
        batch: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._media = media
        self._storage = storage
        self._grace = grace
        self._batch = batch
        self._clock = clock

    def sweep(self) -> SweepResult:
        candidates = self._media.older_than(self._clock() - self._grace, limit=self._batch)
        used = referenced({item.url for item in candidates})
        orphans = [item for item in candidates if item.url not in used]
        for item in orphans:
            self._storage.destroy(item.public_id)
        self._media.delete(item.pk for item in orphans)
        return SweepResult(checked=len(candidates), deleted=len(orphans))


# account retention: the files a client uploaded for themselves (avatar, message attachments)
# go with their personal data, once nothing points to them any more
class OwnerFilesEraser:
    def __init__(self, media: MediaRepository, storage: MediaStorage) -> None:
        self._media = media
        self._storage = storage

    def erase(self, owner_id: int) -> int:
        items = self._media.owned_by(owner_id, purposes=[purpose.value for purpose in PERSONAL])
        used = referenced({item.url for item in items})
        unused = [item for item in items if item.url not in used]
        for item in unused:
            self._storage.destroy(item.public_id)
        return self._media.delete(item.pk for item in unused)

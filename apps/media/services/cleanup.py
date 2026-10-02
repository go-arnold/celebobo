from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.media.repositories import MediaRepository
from apps.media.services.contracts import MediaStorage
from apps.media.services.references import referenced


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

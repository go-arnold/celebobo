from collections.abc import Iterable
from datetime import datetime
from typing import Any

from apps.media.models import UploadedMedia


class MediaRepository:
    def claim(self, public_id: str, defaults: dict[str, Any]) -> UploadedMedia:
        media, _ = UploadedMedia.objects.get_or_create(public_id=public_id, defaults=defaults)
        return media

    def older_than(self, before: datetime, *, limit: int) -> list[UploadedMedia]:
        return list(UploadedMedia.objects.filter(created_at__lt=before).order_by("pk")[:limit])

    def owned_by(self, owner_id: int, *, purposes: Iterable[str]) -> list[UploadedMedia]:
        return list(
            UploadedMedia.objects.filter(owner_id=owner_id, purpose__in=list(purposes)).order_by(
                "pk"
            )
        )

    def delete(self, media_ids: Iterable[int]) -> int:
        deleted, _ = UploadedMedia.objects.filter(pk__in=list(media_ids)).delete()
        return deleted

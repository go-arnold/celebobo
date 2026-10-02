from typing import Any

from apps.media.models import UploadedMedia


class MediaRepository:
    def claim(self, public_id: str, defaults: dict[str, Any]) -> UploadedMedia:
        media, _ = UploadedMedia.objects.get_or_create(public_id=public_id, defaults=defaults)
        return media

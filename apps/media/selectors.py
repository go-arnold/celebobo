from collections.abc import Iterable

from apps.media.domain.policies import UploadPurpose
from apps.media.domain.uploads import StoredMedia
from apps.media.models import UploadedMedia


class MediaSelector:
    def urls(self, media_ids: Iterable[int], purpose: UploadPurpose) -> dict[int, str]:
        return dict(
            UploadedMedia.objects.filter(pk__in=list(media_ids), purpose=purpose.value).values_list(
                "pk", "url"
            )
        )

    def owned_url(self, media_id: int, *, owner_id: int, purpose: UploadPurpose) -> str | None:
        return (
            UploadedMedia.objects.filter(pk=media_id, owner_id=owner_id, purpose=purpose.value)
            .values_list("url", flat=True)
            .first()
        )


def to_stored(media: UploadedMedia) -> StoredMedia:
    return StoredMedia(
        id=media.pk,
        purpose=UploadPurpose(media.purpose),
        public_id=media.public_id,
        url=media.url,
        format=media.format,
        bytes=media.bytes,
        width=media.width,
        height=media.height,
    )

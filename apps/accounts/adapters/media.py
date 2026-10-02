from apps.media.domain.policies import UploadPurpose
from apps.media.selectors import MediaSelector


class MediaAvatars:
    def url_for(self, owner_id: int, upload_id: int) -> str | None:
        return MediaSelector().owned_url(upload_id, owner_id=owner_id, purpose=UploadPurpose.AVATAR)

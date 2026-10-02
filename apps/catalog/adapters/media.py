from collections.abc import Sequence

from apps.media.domain.policies import UploadPurpose
from apps.media.selectors import MediaSelector


class UploadedMediaUrls:
    def product_images(self, media_ids: Sequence[int]) -> dict[int, str]:
        return MediaSelector().urls(media_ids, UploadPurpose.PRODUCT_IMAGE)

    def category_images(self, media_ids: Sequence[int]) -> dict[int, str]:
        return MediaSelector().urls(media_ids, UploadPurpose.CATEGORY_IMAGE)

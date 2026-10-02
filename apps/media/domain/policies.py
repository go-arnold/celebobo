from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

IMAGE_FORMATS = ("jpg", "jpeg", "png", "webp")
MEGABYTE = 1024 * 1024


class UploadPurpose(StrEnum):
    PRODUCT_IMAGE = "product_image"
    CATEGORY_IMAGE = "category_image"
    AVATAR = "avatar"
    MESSAGE_ATTACHMENT = "message_attachment"


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    purpose: UploadPurpose
    folder: str
    permission: str
    max_bytes: int
    formats: tuple[str, ...]
    transformation: str


POLICIES: Mapping[UploadPurpose, UploadPolicy] = MappingProxyType(
    {
        UploadPurpose.PRODUCT_IMAGE: UploadPolicy(
            purpose=UploadPurpose.PRODUCT_IMAGE,
            folder="products",
            permission="products.manage",
            max_bytes=8 * MEGABYTE,
            formats=IMAGE_FORMATS,
            transformation="c_limit,w_1600,h_1600/q_auto:good",
        ),
        UploadPurpose.CATEGORY_IMAGE: UploadPolicy(
            purpose=UploadPurpose.CATEGORY_IMAGE,
            folder="categories",
            permission="categories.manage",
            max_bytes=4 * MEGABYTE,
            formats=IMAGE_FORMATS,
            transformation="c_limit,w_1200,h_1200/q_auto:good",
        ),
        UploadPurpose.AVATAR: UploadPolicy(
            purpose=UploadPurpose.AVATAR,
            folder="avatars",
            permission="media.upload",
            max_bytes=2 * MEGABYTE,
            formats=IMAGE_FORMATS,
            transformation="c_fill,g_face,w_400,h_400/q_auto",
        ),
        UploadPurpose.MESSAGE_ATTACHMENT: UploadPolicy(
            purpose=UploadPurpose.MESSAGE_ATTACHMENT,
            folder="attachments",
            permission="media.upload",
            max_bytes=5 * MEGABYTE,
            formats=IMAGE_FORMATS,
            transformation="c_limit,w_1600,h_1600/q_auto",
        ),
    }
)


def policy_for(purpose: UploadPurpose) -> UploadPolicy:
    return POLICIES[purpose]

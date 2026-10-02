from dataclasses import dataclass

from apps.media.domain.policies import UploadPurpose


@dataclass(frozen=True, slots=True, kw_only=True)
class UploadSignature:
    upload_url: str
    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    allowed_formats: str
    transformation: str
    max_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CompletedUpload:
    purpose: UploadPurpose
    public_id: str
    version: int
    signature: str
    format: str
    bytes: int
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredMedia:
    id: int
    purpose: UploadPurpose
    public_id: str
    url: str
    format: str
    bytes: int
    width: int | None
    height: int | None

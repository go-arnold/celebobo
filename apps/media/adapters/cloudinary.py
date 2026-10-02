import hashlib
import hmac
import time
from collections.abc import Mapping

import httpx

from apps.media.conf import MediaSettings, media_settings
from apps.media.domain.errors import StorageNotConfigured, StorageUnavailable
from apps.media.domain.policies import UploadPolicy
from apps.media.domain.uploads import CompletedUpload, UploadSignature
from apps.media.services.uploads import storage_registry

API_BASE = "https://api.cloudinary.com/v1_1"
DELIVERY_BASE = "https://res.cloudinary.com"
DESTROY_TIMEOUT = 10.0
HTTP_ERROR = 400


def sign(params: Mapping[str, object], secret: str) -> str:
    payload = "&".join(f"{key}={params[key]}" for key in sorted(params) if params[key] != "")
    return hashlib.sha1(f"{payload}{secret}".encode(), usedforsecurity=False).hexdigest()


@storage_registry.register("cloudinary")
class CloudinaryStorage:
    def __init__(self, settings: MediaSettings | None = None) -> None:
        self._fixed_settings = settings

    @property
    def _settings(self) -> MediaSettings:
        return self._fixed_settings or media_settings()

    def sign_upload(self, policy: UploadPolicy, *, timestamp: int) -> UploadSignature:
        self._ensure_configured()
        folder = self.folder_for(policy)
        allowed = ",".join(policy.formats)
        params = {
            "allowed_formats": allowed,
            "folder": folder,
            "timestamp": timestamp,
            "transformation": policy.transformation,
        }
        return UploadSignature(
            upload_url=f"{API_BASE}/{self._settings.cloud_name}/image/upload",
            cloud_name=self._settings.cloud_name,
            api_key=self._settings.api_key,
            timestamp=timestamp,
            signature=sign(params, self._settings.api_secret),
            folder=folder,
            allowed_formats=allowed,
            transformation=policy.transformation,
            max_bytes=policy.max_bytes,
        )

    def verify(self, upload: CompletedUpload) -> bool:
        self._ensure_configured()
        expected = sign(
            {"public_id": upload.public_id, "version": upload.version}, self._settings.api_secret
        )
        return hmac.compare_digest(expected, upload.signature)

    def folder_for(self, policy: UploadPolicy) -> str:
        return f"{self._settings.root_folder.strip('/')}/{policy.folder}"

    def delivery_url(self, upload: CompletedUpload) -> str:
        return (
            f"{DELIVERY_BASE}/{self._settings.cloud_name}/image/upload/"
            f"v{upload.version}/{upload.public_id}.{upload.format}"
        )

    def destroy(self, public_id: str) -> None:
        self._ensure_configured()
        timestamp = int(time.time())
        params = {"public_id": public_id, "timestamp": timestamp}
        response = httpx.post(
            f"{API_BASE}/{self._settings.cloud_name}/image/destroy",
            data={
                **params,
                "api_key": self._settings.api_key,
                "signature": sign(params, self._settings.api_secret),
            },
            timeout=DESTROY_TIMEOUT,
        )
        if response.status_code >= HTTP_ERROR:
            raise StorageUnavailable

    def _ensure_configured(self) -> None:
        settings = self._settings
        if not (settings.cloud_name and settings.api_key and settings.api_secret):
            raise StorageNotConfigured

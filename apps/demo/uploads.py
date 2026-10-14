import time
from dataclasses import dataclass

import httpx
from django.core.management.base import CommandError
from django.db.models import Q

from apps.accounts.models import User
from apps.media.adapters.cloudinary import API_BASE, sign
from apps.media.conf import media_settings
from apps.media.models import UploadedMedia
from core.api.actor import actor_from_user
from core.domain.actor import Actor, Role

UPLOAD_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class ImageStore:
    owner_id: int
    folder: str = "seed"

    @property
    def enabled(self) -> bool:
        settings = media_settings()
        return bool(settings.cloud_name and settings.api_key and settings.api_secret)

    def upload(self, name: str, content: bytes, *, purpose: str) -> int | None:
        if not self.enabled:
            return None
        settings = media_settings()
        folder = f"{settings.root_folder.strip('/')}/{self.folder}"
        params = {
            "folder": folder,
            "overwrite": "true",
            "public_id": name,
            "timestamp": int(time.time()),
        }
        response = httpx.post(
            f"{API_BASE}/{settings.cloud_name}/image/upload",
            data={
                **params,
                "api_key": settings.api_key,
                "signature": sign(params, settings.api_secret),
            },
            files={"file": (f"{name}.jpg", content, "image/jpeg")},
            timeout=UPLOAD_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        media, _ = UploadedMedia.objects.update_or_create(
            public_id=body["public_id"],
            defaults={
                "owner_id": self.owner_id,
                "purpose": purpose,
                "url": body["secure_url"],
                "format": body.get("format", "jpg"),
                "bytes": body.get("bytes", len(content)),
                "width": body.get("width"),
                "height": body.get("height"),
            },
        )
        return media.pk


# command-line uploads are signed by the first administrator, as if made from the back office
def admin_store(folder: str) -> tuple[Actor, ImageStore]:
    admin = (
        User.objects.filter(Q(is_superuser=True) | Q(role=Role.ADMIN.value)).order_by("pk").first()
    )
    if admin is None:
        raise CommandError("Aucun administrateur pour signer les envois.")
    store = ImageStore(owner_id=admin.pk, folder=folder)
    if not store.enabled:
        raise CommandError("Cloudinary n'est pas configuré.")
    return actor_from_user(admin), store


def upload(store: ImageStore, name: str, content: bytes, *, purpose: str) -> int:
    media_id = store.upload(name, content, purpose=purpose)
    if media_id is None:
        raise CommandError("Cloudinary n'est pas configuré.")
    return media_id

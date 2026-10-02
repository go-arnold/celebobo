from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.catalog.models import ProductImage
from apps.catalog.tests.factories import ProductFactory
from apps.media.adapters import cloudinary
from apps.media.adapters.cloudinary import CloudinaryStorage
from apps.media.conf import MediaSettings
from apps.media.domain.errors import StorageUnavailable
from apps.media.facades import MediaMaintenanceFacade
from apps.media.models import UploadedMedia
from apps.media.services.contracts import MediaStorage
from apps.media.tasks import sweep_orphans
from core.container import container

pytestmark = pytest.mark.django_db


class RecordingStorage:
    def __init__(self) -> None:
        self.destroyed: list[str] = []

    def destroy(self, public_id: str) -> None:
        self.destroyed.append(public_id)


@pytest.fixture
def storage():
    recording = RecordingStorage()
    with container.override(MediaStorage, recording):
        yield recording


def media(owner, name, *, age_hours=48):
    item = UploadedMedia.objects.create(
        owner=owner,
        purpose="product_image",
        public_id=f"celebobo/products/{name}",
        url=f"https://res.cloudinary.com/demo/image/upload/v1/{name}.jpg",
        format="jpg",
        bytes=1000,
    )
    UploadedMedia.objects.filter(pk=item.pk).update(
        created_at=timezone.now() - timedelta(hours=age_hours)
    )
    return item


def test_unreferenced_uploads_are_deleted_after_a_grace_period(storage):
    owner = UserFactory.create()
    product = ProductFactory.create()
    used = media(owner, "used")
    orphan = media(owner, "orphan")
    fresh = media(owner, "fresh", age_hours=1)
    avatar = media(owner, "avatar")
    ProductImage.objects.create(product=product, url=used.url, position=5)
    owner.avatar = avatar.url
    owner.save(update_fields=["avatar"])

    result = container.resolve(MediaMaintenanceFacade).sweep_orphans()

    assert (result.checked, result.deleted) == (3, 1)
    assert storage.destroyed == [orphan.public_id]
    assert set(UploadedMedia.objects.values_list("pk", flat=True)) == {used.pk, fresh.pk, avatar.pk}


def test_the_beat_task_reports_deletions(storage):
    media(UserFactory.create(), "orphan")

    assert sweep_orphans() == 1


def test_cloudinary_destroy_is_signed(monkeypatch):
    calls = []

    def fake_post(url, *, data, timeout):
        calls.append((url, data))
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("apps.media.adapters.cloudinary.httpx.post", fake_post)
    settings = MediaSettings(cloud_name="demo", api_key="key", api_secret="secret")

    CloudinaryStorage(settings).destroy("celebobo/products/a")

    url, data = calls[0]
    assert url == "https://api.cloudinary.com/v1_1/demo/image/destroy"
    assert data["public_id"] == "celebobo/products/a"
    assert data["signature"] == cloudinary.sign(
        {"public_id": "celebobo/products/a", "timestamp": data["timestamp"]}, "secret"
    )


def test_cloudinary_errors_surface(monkeypatch):
    def failing_post(*_args, **_kwargs):
        return SimpleNamespace(status_code=500)

    monkeypatch.setattr("apps.media.adapters.cloudinary.httpx.post", failing_post)
    settings = MediaSettings(cloud_name="demo", api_key="key", api_secret="secret")

    with pytest.raises(StorageUnavailable):
        CloudinaryStorage(settings).destroy("a")

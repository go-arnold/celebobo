from io import StringIO

import httpx
import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory
from apps.catalog.models import Product
from apps.demo.people import DemoPerson, email_for
from apps.demo.uploads import ImageStore
from apps.media.models import UploadedMedia
from apps.orders.models import Order
from apps.sales.models import Sale


def seed() -> str:
    out = StringIO()
    call_command("seed_demo", "--admin-email", "admin@celebobo.test", "--no-images", stdout=out)
    return out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_seed_fills_an_empty_database_and_refuses_a_second_run():
    output = seed()

    assert "Comptes de démonstration" in output
    assert User.objects.filter(email="admin@celebobo.test", is_superuser=True).exists()
    assert Product.objects.count() >= 20
    assert Order.objects.filter(status="delivered").exists()
    assert Sale.objects.exists()
    assert not User.objects.filter(email__regex=r"[^\x00-\x7F]").exists()
    with pytest.raises(CommandError):
        seed()


def test_emails_drop_accents():
    person = DemoPerson("Joël", "Kalé", "+243810000000", "Kinshasa", "Gombe")

    assert email_for(person, "celebobo.test") == "joel.kale@celebobo.test"


@pytest.mark.django_db
def test_upload_signs_the_request_and_records_the_media(monkeypatch):
    owner = AdminFactory.create()
    sent: dict[str, object] = {}

    def post(url, *, data, files, timeout):
        sent.update(url=url, data=data)
        body = {
            "public_id": "celebobo-test/seed/phone",
            "secure_url": "https://res.cloudinary.com/demo/image/upload/phone.jpg",
            "format": "jpg",
            "bytes": 120,
            "width": 800,
            "height": 800,
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)

    media_id = ImageStore(owner_id=owner.pk).upload("phone", b"jpeg", purpose="product")

    assert media_id is not None
    media = UploadedMedia.objects.get(pk=media_id)
    assert media.url.endswith("phone.jpg")
    assert media.owner_id == owner.pk
    data = sent["data"]
    assert str(sent["url"]).endswith("/demo/image/upload")
    assert isinstance(data, dict)
    assert data["folder"] == "celebobo-test/seed"
    assert data["signature"]

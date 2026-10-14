from io import StringIO
from pathlib import Path

import httpx
import pytest
from django.core.management import CommandError, call_command

from apps.accounts.tests.factories import AdminFactory
from apps.catalog.tests.factories import ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def cloudinary(monkeypatch):
    sent: list[str] = []

    def post(url, *, data, files, timeout):
        public_id = f"{data['folder']}/{data['public_id']}"
        sent.append(public_id)
        body = {
            "public_id": public_id,
            "secure_url": f"https://res.cloudinary.com/demo/image/upload/{public_id}.jpg",
            "format": "jpg",
            "bytes": 120,
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    return sent


def folder(tmp_path: Path, **products: int) -> Path:
    for slug, count in products.items():
        (tmp_path / slug).mkdir()
        for position in range(count):
            (tmp_path / slug / f"{position + 1}.jpg").write_bytes(b"jpeg")
    return tmp_path


def test_replaces_the_images_in_file_order(tmp_path, cloudinary):
    AdminFactory.create()
    product = ProductFactory.create(slug="galaxy-a55")

    call_command("attach_product_images", folder(tmp_path, **{"galaxy-a55": 2}), stdout=StringIO())

    urls = list(product.images.values_list("url", flat=True))
    assert [url.rsplit("/", 1)[-1] for url in urls] == ["galaxy-a55-1.jpg", "galaxy-a55-2.jpg"]
    assert cloudinary == [
        "celebobo-test/products/galaxy-a55-1",
        "celebobo-test/products/galaxy-a55-2",
    ]


def test_dry_run_changes_nothing(tmp_path, cloudinary):
    product = ProductFactory.create(slug="galaxy-a55")
    before = list(product.images.values_list("url", flat=True))

    call_command(
        "attach_product_images",
        folder(tmp_path, **{"galaxy-a55": 1}),
        "--dry-run",
        stdout=StringIO(),
    )

    assert list(product.images.values_list("url", flat=True)) == before
    assert cloudinary == []


@pytest.mark.parametrize("products", [{"unknown": 1}, {"galaxy-a55": 5}])
def test_rejects_unknown_products_and_too_many_images(tmp_path, cloudinary, products):
    ProductFactory.create(slug="galaxy-a55")

    with pytest.raises(CommandError):
        call_command("attach_product_images", folder(tmp_path, **products), stdout=StringIO())

    assert cloudinary == []

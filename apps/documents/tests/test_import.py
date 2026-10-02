import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Product, StockMovement
from apps.documents.domain.errors import InvalidImportFile
from apps.documents.models import Job
from apps.documents.services.importer import parse_csv

pytestmark = pytest.mark.django_db

IMPORT = "/api/v1/bo/products/import/"
CSV = (
    "slug;name;category;price;sale_price;cost_price;stock;is_active\n"
    "galaxy-a55;Galaxy A55 5G;smartphones;125,00;;85;30;1\n"
    ";Redmi Note 13;smartphones;180;150;120;12;oui\n"
    ";;inconnue;-3;;;x;peut-être\n"
)


def upload(content: str, name: str = "produits.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content.encode(), content_type="text/csv")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"name,price\nA,1\n", "Colonnes manquantes : category."),
        ("name,category,price\n".encode("utf-16"), "UTF-8"),
        (b"name,category,price\n", "aucune ligne"),
        (b"name,category,price\n" + b"A,b,1\n" * 3, "2 lignes maximum"),
    ],
)
def test_rejects_unusable_files(content, message):
    with pytest.raises(InvalidImportFile) as error:
        parse_csv(content, max_rows=2, max_bytes=10_000)

    assert message in error.value.errors["file"][0]


def test_rejects_large_files():
    with pytest.raises(InvalidImportFile):
        parse_csv(b"x" * 11, max_rows=2, max_bytes=10)


def test_dry_run_reports_without_writing(as_user, manager, phone, run_jobs):
    with run_jobs():
        response = as_user(manager).post(
            IMPORT, {"file": upload(CSV), "dry_run": "true"}, format="multipart"
        )

    assert response.status_code == 202
    job = Job.objects.get()
    assert job.status == "done"
    assert job.summary["dry_run"] is True
    assert (job.summary["created"], job.summary["updated"]) == (1, 1)
    assert job.summary["error_count"] == 1
    assert set(job.summary["errors"][0]["errors"]) == {
        "name",
        "category",
        "price",
        "stock",
        "is_active",
    }
    assert job.summary["errors"][0]["row"] == 4
    assert Product.objects.count() == 1
    assert job.upload is None


def test_import_creates_and_updates_through_the_catalogue(as_user, manager, phone, run_jobs):
    with run_jobs():
        as_user(manager).post(IMPORT, {"file": upload(CSV)}, format="multipart")

    phone.refresh_from_db()
    assert phone.name == "Galaxy A55 5G"
    assert str(phone.price) == "125.00"
    assert phone.stock == 30
    created = Product.objects.get(name="Redmi Note 13")
    assert created.stock == 12
    assert str(created.sale_price) == "150.00"
    assert StockMovement.objects.filter(product=phone, note="Import CSV").exists()
    assert Job.objects.get().summary["created"] == 1


def test_invalid_files_are_refused_before_queueing(as_user, manager):
    response = as_user(manager).post(IMPORT, {"file": upload("a,b\n1,2\n")}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.json()["errors"]
    assert not Job.objects.exists()


def test_resellers_cannot_import(as_user, reseller):
    response = as_user(reseller).post(IMPORT, {"file": upload(CSV)}, format="multipart")

    assert response.status_code == 403

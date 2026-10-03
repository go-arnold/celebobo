from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.content.models import Banner, FaqEntry, Page

pytestmark = pytest.mark.django_db


def test_home_assembles_banners_and_product_sections(api):
    phones = CategoryFactory.create(name="Smartphones", slug="smartphones")
    deal = ProductFactory.create(
        name="Galaxy A55", category=phones, price=Decimal("300"), sale_price=Decimal("250")
    )
    ProductFactory.create(name="Redmi 13", category=phones)
    now = timezone.now()
    Banner.objects.create(title="Soldes", image="https://img.test/a.jpg", position=1)
    Banner.objects.create(
        title="Bientôt", image="https://img.test/b.jpg", starts_at=now + timedelta(days=1)
    )
    Banner.objects.create(
        title="Fini", image="https://img.test/c.jpg", ends_at=now - timedelta(days=1)
    )
    Banner.objects.create(title="Caché", image="https://img.test/d.jpg", is_active=False)

    body = api.get("/api/v1/home/").json()

    assert [banner["title"] for banner in body["banners"]] == ["Soldes"]
    assert [card["id"] for card in body["deals"]] == [deal.pk]
    assert {card["name"] for card in body["new_arrivals"]} == {"Galaxy A55", "Redmi 13"}
    block = next(item for item in body["categories"] if item["category"]["slug"] == "smartphones")
    assert len(block["products"]) == 2


def test_public_settings_hide_the_newsletter_code(api, site):
    body = api.get("/api/v1/settings/public/").json()

    assert body["hotline"] == "+243 81 000 0000"
    assert body["whatsapp_url"] == "https://wa.me/243821112222"
    assert body["payment_methods"] == ["orange_money", "cash"]
    assert body["shipping"] == {"free_threshold": "199.00", "flat_fee": "2.98"}
    assert "newsletter_code" not in body


def test_public_settings_are_cacheable(api):
    assert "public" in api.get("/api/v1/settings/public/")["Cache-Control"]


def test_public_settings_have_defaults(api):
    assert api.get("/api/v1/settings/public/").json()["usd_to_cdf"] == "2800.00"


def test_pages_only_show_published_content(api):
    Page.objects.create(slug="a-propos", title="À propos", body="# Qui sommes-nous", position=1)
    Page.objects.create(slug="brouillon", title="Brouillon", body="…", is_published=False)

    listing = api.get("/api/v1/pages/").json()
    page = api.get("/api/v1/pages/a-propos/").json()

    assert [item["slug"] for item in listing] == ["a-propos"]
    assert "body" not in listing[0]
    assert page["body"] == "# Qui sommes-nous"
    assert api.get("/api/v1/pages/brouillon/").status_code == 404


def test_faq_is_grouped_by_category(api):
    FaqEntry.objects.create(question="Délais ?", answer="24-48 h", category="Livraison", position=1)
    FaqEntry.objects.create(question="Frais ?", answer="2,98 $", category="Livraison", position=2)
    FaqEntry.objects.create(question="Paiement ?", answer="Orange Money", category="Paiement")
    FaqEntry.objects.create(question="Secret", answer="…", category="Paiement", is_published=False)

    body = api.get("/api/v1/faq/").json()

    assert [(group["category"], len(group["entries"])) for group in body] == [
        ("Livraison", 2),
        ("Paiement", 1),
    ]

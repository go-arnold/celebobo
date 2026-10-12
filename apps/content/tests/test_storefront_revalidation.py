from decimal import Decimal
from typing import Any

import httpx
import pytest
from celery.exceptions import Retry
from django.test import override_settings

from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.content.domain.storefront import category_tags, product_tags, section_tags
from apps.content.facades import StorefrontFacade
from apps.content.services.storefront import PendingTags
from apps.content.tasks import revalidate_storefront

pytestmark = pytest.mark.django_db

URL = "http://frontend.test/revalidate"
SECRET = "revalidate-secret"
FRONTEND = {"REVALIDATE_URL": URL, "REVALIDATE_SECRET": SECRET, "DEBOUNCE": 0}


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict[str, Any]] = []

    def post(url, *, json, headers, timeout):
        calls.append({"url": url, "tags": json["tags"], "headers": headers, "timeout": timeout})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr("apps.content.adapters.storefront.httpx.post", post)
    return calls


@pytest.fixture
def phones(db):
    return CategoryFactory.create(slug="smartphones")


@override_settings(STOREFRONT=FRONTEND)
def test_product_change_revalidates_its_pages(
    as_user, manager, phones, sent, django_capture_on_commit_callbacks
):
    product = ProductFactory.create(slug="galaxy-a55", category=phones, price=Decimal(300))

    with django_capture_on_commit_callbacks(execute=True):
        response = as_user(manager).patch(
            f"/api/v1/bo/products/{product.pk}/", {"sale_price": "250.00"}, format="json"
        )

    assert response.status_code == 200
    (call,) = sent
    assert call["url"] == URL
    assert call["headers"] == {"X-Revalidate-Secret": SECRET}
    assert call["timeout"] == 5
    assert call["tags"] == ["category:smartphones", "home", "product:galaxy-a55", "sitemap"]


@override_settings(STOREFRONT=FRONTEND)
def test_removed_product_is_revalidated_too(
    as_user, admin, phones, sent, django_capture_on_commit_callbacks
):
    product = ProductFactory.create(slug="galaxy-a55", category=phones)

    with django_capture_on_commit_callbacks(execute=True):
        as_user(admin).delete(f"/api/v1/bo/products/{product.pk}/")

    assert "product:galaxy-a55" in sent[-1]["tags"]


@override_settings(STOREFRONT=FRONTEND)
def test_site_content_changes(as_user, admin, site, sent, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        as_user(admin).patch("/api/v1/bo/settings/", {"hotline": "+243 81 999 9999"})
    with django_capture_on_commit_callbacks(execute=True):
        as_user(admin).post(
            "/api/v1/bo/pages/", {"slug": "guide", "title": "Guide", "body": "…"}, format="json"
        )

    assert [call["tags"] for call in sent] == [["home"], ["sitemap"]]


def test_nothing_is_sent_without_a_frontend_url(
    as_user, manager, phones, sent, django_capture_on_commit_callbacks
):
    product = ProductFactory.create(category=phones)

    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).patch(f"/api/v1/bo/products/{product.pk}/", {"name": "Nouveau nom"})

    assert sent == []


@pytest.fixture
def frontend_down(monkeypatch):
    attempts: list[str] = []

    def down(url, **_):
        attempts.append(url)
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("apps.content.adapters.storefront.httpx.post", down)
    return attempts


@override_settings(STOREFRONT=FRONTEND)
def test_unreachable_frontend_never_blocks_the_write(
    as_user, manager, phones, frontend_down, django_capture_on_commit_callbacks
):
    product = ProductFactory.create(category=phones)

    with django_capture_on_commit_callbacks(execute=True):
        response = as_user(manager).patch(
            f"/api/v1/bo/products/{product.pk}/", {"name": "Nouveau nom"}
        )

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.name == "Nouveau nom"
    assert frontend_down


@override_settings(STOREFRONT=FRONTEND)
def test_failed_deliveries_are_retried_with_backoff(frontend_down, monkeypatch):
    retries: list[dict[str, Any]] = []

    def retry(**options):
        retries.append(options)
        return Retry()

    monkeypatch.setattr(revalidate_storefront, "retry", retry)

    with pytest.raises(Retry):
        revalidate_storefront.apply(args=(["home"],), throw=True)

    (options,) = retries
    assert options["args"] == [["home"]]
    assert options["countdown"] == 2
    assert options["max_retries"] == 3


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Catalog:
    def product_locations(self, product_ids) -> list[tuple[str, str]]:
        return [(f"produit-{product_id}", "smartphones") for product_id in product_ids]

    def category_slug(self, category_id: int) -> str:
        return "smartphones"


class Recorder:
    def __init__(self) -> None:
        self.sent: list[list[str]] = []

    def revalidate(self, tags) -> None:
        self.sent.append(list(tags))


def storefront(clock: Clock, scheduled: list[int], recorder: Recorder) -> StorefrontFacade:
    return StorefrontFacade(
        catalog=Catalog(),  # type: ignore[arg-type]
        pending=PendingTags(clock=clock, debounce=5, max_wait=60),
        revalidator=recorder,
        schedule=scheduled.append,
        debounce=5,
    )


def test_a_burst_of_changes_is_sent_once_when_it_stops():
    clock, scheduled, recorder = Clock(), list[int](), Recorder()
    front = storefront(clock, scheduled, recorder)

    for product_id in (1, 2, 3):
        front.products_changed([product_id])
        clock.now += 2
    early = front.due_tags()
    clock.now += 5
    due = front.due_tags()
    front.send(due)

    assert scheduled == [5, 3]
    assert early == []
    assert recorder.sent == [
        [
            "category:smartphones",
            "home",
            "product:produit-1",
            "product:produit-2",
            "product:produit-3",
            "sitemap",
        ]
    ]
    assert front.due_tags() == []


def test_a_steady_stream_is_still_sent_after_the_maximum_wait():
    clock, scheduled, recorder = Clock(), list[int](), Recorder()
    front = storefront(clock, scheduled, recorder)

    for _ in range(40):
        front.section_changed("banners")
        clock.now += 2

    assert front.due_tags() == ["home"]


def test_tags():
    assert product_tags("a55", "smartphones") == (
        "product:a55",
        "category:smartphones",
        "home",
        "sitemap",
    )
    assert category_tags("audio") == ("category:audio", "home", "sitemap")
    assert section_tags("banners") == ("home",)
    assert section_tags("pages") == ("sitemap",)

from decimal import Decimal

import pytest

from apps.assistant.adapters.offline import HashingEmbedder
from apps.assistant.domain.enums import EmbeddingTask
from apps.assistant.domain.queries import ProductQuery
from apps.assistant.facades import AssistantInsightsFacade
from apps.assistant.models import ProductEmbedding
from apps.assistant.selectors import VectorSelector
from apps.catalog.models import Product
from core.container import container

pytestmark = pytest.mark.django_db


def nearest(text: str, **filters) -> list[int]:
    (vector,) = HashingEmbedder().embed([text], task=EmbeddingTask.QUERY)
    return VectorSelector().nearest(vector, ProductQuery(query=text, **filters), limit=3)


def test_hashing_embeddings_are_normalised_and_stable():
    first, second = HashingEmbedder().embed(
        ["Téléphone Samsung", "telephone samsung"], task=EmbeddingTask.DOCUMENT
    )

    assert first == second
    assert len(first) == 768
    assert round(sum(value * value for value in first), 6) == 1.0


def test_semantic_search_ranks_and_filters(catalogue):
    galaxy, redmi, case = catalogue["galaxy"], catalogue["redmi"], catalogue["case"]

    assert nearest("smartphone samsung")[0] == galaxy.pk
    assert nearest("coque de protection")[0] == case.pk
    assert nearest("smartphone", max_price=Decimal("200")) == [redmi.pk, case.pk]
    assert nearest("smartphone", on_sale=True) == [galaxy.pk]
    assert set(nearest("téléphone", category="smartphones")) == {galaxy.pk, redmi.pk}


def test_embeddings_track_catalogue_changes(catalogue):
    insights = container.resolve(AssistantInsightsFacade)
    galaxy, case = catalogue["galaxy"], catalogue["case"]

    unchanged = insights.refresh_embeddings([galaxy.pk])
    Product.objects.filter(pk=galaxy.pk).update(sale_price=None, current_price=Decimal("320.00"))
    repriced = insights.refresh_embeddings([galaxy.pk])
    Product.objects.filter(pk=galaxy.pk).update(name="Samsung Galaxy A56")
    renamed = insights.refresh_embeddings([galaxy.pk])
    Product.objects.filter(pk=case.pk).update(is_active=False)
    hidden = insights.refresh_embeddings([case.pk])

    assert unchanged == {"embedded": 0, "removed": 0, "unchanged": 1}
    assert repriced["unchanged"] == 1
    assert ProductEmbedding.objects.get(pk=galaxy.pk).on_sale is False
    assert renamed["embedded"] == 1
    assert "A56" in ProductEmbedding.objects.get(pk=galaxy.pk).embedded_text
    assert hidden["removed"] == 1


def test_product_events_refresh_embeddings(
    as_user, manager, catalogue, django_capture_on_commit_callbacks
):
    redmi = catalogue["redmi"]
    with django_capture_on_commit_callbacks(execute=True):
        as_user(manager).patch(
            f"/api/v1/bo/products/{redmi.pk}/", {"name": "Xiaomi Redmi Note 14"}, format="json"
        )

    assert "Note 14" in ProductEmbedding.objects.get(pk=redmi.pk).embedded_text


def test_admins_can_rebuild_every_embedding(
    as_user, admin, manager, catalogue, django_capture_on_commit_callbacks
):
    ProductEmbedding.objects.all().delete()

    with django_capture_on_commit_callbacks(execute=True):
        response = as_user(admin).post("/api/v1/bo/embeddings/reindex/")

    assert response.status_code == 202
    assert ProductEmbedding.objects.count() == 3
    assert as_user(manager).post("/api/v1/bo/embeddings/reindex/").status_code == 403

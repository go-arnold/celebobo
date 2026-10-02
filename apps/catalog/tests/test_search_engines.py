from collections.abc import Mapping, MutableMapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone
from meilisearch.errors import MeilisearchCommunicationError

from apps.catalog.adapters.database import DatabaseSearch, SameCategoryRelated
from apps.catalog.adapters.meilisearch import (
    INDEX_SETTINGS,
    MeilisearchIndex,
    MeilisearchSearch,
    filters,
)
from apps.catalog.domain.enums import Badge, ProductOrdering
from apps.catalog.domain.errors import SearchUnavailable
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, FeatureFactory, ProductFactory


class FakeIndex:
    def __init__(self, response: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self.response = response or {}
        self.fail = fail
        self.calls: list[tuple[str, Any]] = []

    def search(self, query: str, opt_params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self._record("search", (query, opt_params))
        return self.response

    def update_settings(self, body: MutableMapping[str, Any]) -> None:
        self._record("update_settings", body)

    def add_documents(
        self, documents: Sequence[Mapping[str, Any]], primary_key: str | None = None
    ) -> None:
        self._record("add_documents", (documents, primary_key))

    def delete_documents(self, ids: list[str | int] | None = None) -> None:
        self._record("delete_documents", ids)

    def _record(self, name: str, payload: Any) -> None:
        if self.fail:
            raise MeilisearchCommunicationError("down")
        self.calls.append((name, payload))


class TestMeilisearchAdapter:
    def test_search_builds_filters_sort_and_pagination(self):
        index = FakeIndex({"hits": [{"id": 3}, {"id": 1}], "totalHits": 14})
        query = ProductQuery(
            text="iphone",
            category="smartphones",
            on_sale=True,
            in_stock=False,
            min_price=Decimal("10.50"),
            ordering=ProductOrdering.PRICE_DESC,
            page=2,
            page_size=12,
        )

        page = MeilisearchSearch(lambda: index).search(query)

        assert page.ids == (3, 1)
        assert page.total == 14
        text, params = index.calls[0][1]
        assert text == "iphone"
        assert params == {
            "filter": [
                'category_slug = "smartphones"',
                "on_sale = true",
                "in_stock = false",
                "current_price >= 10.5",
            ],
            "sort": ["current_price:desc"],
            "page": 2,
            "hitsPerPage": 12,
            "attributesToRetrieve": ["id"],
        }

    def test_relevance_has_no_sort(self):
        index = FakeIndex({"hits": []})

        MeilisearchSearch(lambda: index).search(ProductQuery(text="casque"))

        assert index.calls[0][1][1]["sort"] == []

    def test_filters_for_ids_badges_and_dates(self):
        since = datetime(2026, 9, 12, tzinfo=UTC)

        assert filters(ProductQuery(ids=(4, 7), badge=Badge.BEST_SELLER)) == [
            "id IN [4, 7]",
            'badge = "best_seller"',
        ]
        assert filters(ProductQuery(new_since=since, max_price=Decimal(99))) == [
            f"created_at >= {int(since.timestamp())}",
            "current_price <= 99.0",
        ]

    def test_quotes_are_escaped(self):
        assert filters(ProductQuery(category='a"b')) == ['category_slug = "a\\"b"']

    def test_facets_ignore_the_category_filter_for_category_counts(self):
        index = FakeIndex(
            {
                "facetDistribution": {
                    "in_stock": {"true": 5, "false": 2},
                    "on_sale": {"true": 1},
                    "category_slug": {"audio": 3},
                },
                "facetStats": {"current_price": {"min": 9.9, "max": 1399}},
            }
        )

        facets = MeilisearchSearch(lambda: index).facets(ProductQuery(category="audio"))

        scoped, by_category = (call[1][1] for call in index.calls)
        assert scoped["filter"] == ['category_slug = "audio"']
        assert by_category["filter"] == []
        assert facets.in_stock == 5
        assert facets.out_of_stock == 2
        assert facets.on_sale == 1
        assert facets.min_price == Decimal("9.90")
        assert facets.max_price == Decimal("1399.00")
        assert [facet.value for facet in facets.categories] == ["audio"]

    def test_client_errors_become_search_unavailable(self):
        with pytest.raises(SearchUnavailable):
            MeilisearchSearch(lambda: FakeIndex(fail=True)).search(ProductQuery())
        with pytest.raises(SearchUnavailable):
            MeilisearchIndex(lambda: FakeIndex(fail=True)).upsert([{"id": 1}])

    def test_index_operations(self):
        index = FakeIndex()
        adapter = MeilisearchIndex(lambda: index)

        adapter.configure()
        adapter.upsert([{"id": 1}])
        adapter.remove([2, 3])

        assert index.calls == [
            ("update_settings", dict(INDEX_SETTINGS)),
            ("add_documents", ([{"id": 1}], "id")),
            ("delete_documents", [2, 3]),
        ]


@pytest.mark.django_db
class TestDatabaseSearch:
    @pytest.fixture
    def catalog(self) -> dict[str, Product]:
        phones = CategoryFactory.create(name="Smartphones", slug="smartphones")
        audio = CategoryFactory.create(name="Audio", slug="audio")
        products = {
            "iphone": ProductFactory.create(
                name="iPhone 15",
                category=phones,
                price=Decimal(899),
                sale_price=Decimal(749),
                sales_count=40,
            ),
            "galaxy": ProductFactory.create(
                name="Galaxy S24", category=phones, price=Decimal(799), stock=0, sales_count=10
            ),
            "casque": ProductFactory.create(
                name="Casque Sony", category=audio, price=Decimal(199), badge="best_seller"
            ),
        }
        FeatureFactory.create(product=products["casque"], name="Réduction de bruit active")
        ProductFactory.create(name="Ancien modèle", category=phones, is_active=False)
        ProductFactory.create(name="Supprimé", category=phones).delete()
        Product.objects.filter(pk=products["casque"].pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        return products

    def names(self, query: ProductQuery) -> list[str]:
        ids = DatabaseSearch().search(query).ids
        names = dict(Product.objects.filter(pk__in=ids).values_list("pk", "name"))
        return [names[pk] for pk in ids]

    def test_hides_inactive_and_deleted_products(self, catalog):
        page = DatabaseSearch().search(ProductQuery())

        assert page.total == 3

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (ProductQuery(category="audio"), {"Casque Sony"}),
            (ProductQuery(on_sale=True), {"iPhone 15"}),
            (ProductQuery(in_stock=False), {"Galaxy S24"}),
            (ProductQuery(min_price=Decimal(200), max_price=Decimal(760)), {"iPhone 15"}),
            (ProductQuery(badge=Badge.BEST_SELLER), {"Casque Sony"}),
            (ProductQuery(text="bruit"), {"Casque Sony"}),
            (ProductQuery(text="smartphones s24"), {"Galaxy S24"}),
        ],
    )
    def test_filters(self, catalog, query, expected):
        assert set(self.names(query)) == expected

    def test_new_since_uses_creation_date(self, catalog):
        names = self.names(ProductQuery(new_since=timezone.now() - timedelta(days=20)))

        assert set(names) == {"iPhone 15", "Galaxy S24"}

    @pytest.mark.parametrize(
        ("ordering", "expected"),
        [
            (ProductOrdering.PRICE_ASC, ["Casque Sony", "iPhone 15", "Galaxy S24"]),
            (ProductOrdering.BEST_SELLING, ["iPhone 15", "Galaxy S24", "Casque Sony"]),
            (ProductOrdering.NAME, ["Casque Sony", "Galaxy S24", "iPhone 15"]),
        ],
    )
    def test_orderings(self, catalog, ordering, expected):
        assert self.names(ProductQuery(ordering=ordering)) == expected

    def test_relevance_puts_name_prefix_first(self, catalog):
        ProductFactory.create(name="Coque pour iPhone 15")

        assert self.names(ProductQuery(text="iphone"))[0] == "iPhone 15"

    def test_pagination(self, catalog):
        page = DatabaseSearch().search(
            ProductQuery(page=2, page_size=2, ordering=ProductOrdering.NAME)
        )

        assert page.total == 3
        assert len(page.ids) == 1

    def test_facets(self, catalog):
        facets = DatabaseSearch().facets(ProductQuery(category="smartphones"))

        assert {facet.value: facet.count for facet in facets.categories} == {
            "smartphones": 2,
            "audio": 1,
        }
        assert facets.min_price == Decimal("749.00")
        assert facets.max_price == Decimal("799.00")
        assert (facets.in_stock, facets.out_of_stock, facets.on_sale) == (1, 1, 1)

    def test_suggest(self, catalog):
        assert DatabaseSearch().suggest("gal", limit=5) == (catalog["galaxy"].pk,)

    def test_related_products_share_the_category(self, catalog):
        related = SameCategoryRelated().related(catalog["iphone"].pk, limit=8)

        assert related == (catalog["galaxy"].pk,)

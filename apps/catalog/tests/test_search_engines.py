from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.adapters.postgres import PostgresSearch, PostgresSearchIndex, SameCategoryRelated
from apps.catalog.domain.enums import Badge, ProductOrdering
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, FeatureFactory, ProductFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog(reindex) -> dict[str, Product]:
    phones = CategoryFactory.create(name="Smartphones", slug="smartphones")
    audio = CategoryFactory.create(name="Audio", slug="audio")
    chargers = CategoryFactory.create(name="Chargeurs & accessoires", slug="chargeurs")
    products = {
        "iphone": ProductFactory.create(
            name="iPhone 15",
            description="Un téléphone qui permet de photographier en haute définition.",
            category=phones,
            price=Decimal(899),
            sale_price=Decimal(749),
            sales_count=40,
        ),
        "galaxy": ProductFactory.create(
            name="Galaxy S24", category=phones, price=Decimal(799), stock=0, sales_count=10
        ),
        "casque": ProductFactory.create(
            name="Écouteurs Sony", category=audio, price=Decimal(199), badge="best_seller"
        ),
        "chargeur": ProductFactory.create(
            name="Chargeur rapide 65W", category=chargers, price=Decimal(35)
        ),
    }
    FeatureFactory.create(product=products["casque"], name="Réduction de bruit active")
    ProductFactory.create(name="Ancien iPhone", category=phones, is_active=False)
    ProductFactory.create(name="iPhone supprimé", category=phones).delete()
    Product.objects.filter(pk=products["casque"].pk).update(
        created_at=timezone.now() - timedelta(days=40)
    )
    reindex()
    return products


def names(query: ProductQuery) -> list[str]:
    ids = PostgresSearch().search(query).ids
    by_id = dict(Product.all_objects.filter(pk__in=ids).values_list("pk", "name"))
    return [by_id[pk] for pk in ids]


class TestFullTextSearch:
    def test_hides_inactive_and_deleted_products(self, catalog):
        assert names(ProductQuery(text="iphone")) == ["iPhone 15"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("ecouteurs", {"Écouteurs Sony"}),
            ("réduction bruit", {"Écouteurs Sony"}),
            ("chargeurs", {"Chargeur rapide 65W"}),
            ("smartphones", {"iPhone 15", "Galaxy S24"}),
            ("photographier", {"iPhone 15"}),
            ('"galaxy s24"', {"Galaxy S24"}),
            ("galaxy -s24", set()),
        ],
    )
    def test_matches_accents_stems_and_websearch_syntax(self, catalog, text, expected):
        assert set(names(ProductQuery(text=text))) == expected

    def test_name_matches_rank_above_category_matches(self, catalog, reindex):
        ProductFactory.create(name="Pochette en cuir", category=catalog["galaxy"].category)
        ProductFactory.create(name="Smartphone pliable", category=catalog["casque"].category)
        reindex()

        ranked = names(ProductQuery(text="smartphone"))

        assert ranked[0] == "Smartphone pliable"
        assert "Pochette en cuir" in ranked

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            (ProductQuery(category="audio"), {"Écouteurs Sony"}),
            (ProductQuery(on_sale=True), {"iPhone 15"}),
            (ProductQuery(in_stock=False), {"Galaxy S24"}),
            (ProductQuery(min_price=Decimal(200), max_price=Decimal(760)), {"iPhone 15"}),
            (ProductQuery(badge=Badge.BEST_SELLER), {"Écouteurs Sony"}),
            (ProductQuery(text="smartphones", in_stock=True), {"iPhone 15"}),
        ],
    )
    def test_filters(self, catalog, query, expected):
        assert set(names(query)) == expected

    def test_new_since_uses_creation_date(self, catalog):
        recent = names(ProductQuery(new_since=timezone.now() - timedelta(days=20)))

        assert "Écouteurs Sony" not in recent
        assert len(recent) == 3

    @pytest.mark.parametrize(
        ("ordering", "expected"),
        [
            (
                ProductOrdering.PRICE_ASC,
                ["Chargeur rapide 65W", "Écouteurs Sony", "iPhone 15", "Galaxy S24"],
            ),
            (ProductOrdering.BEST_SELLING, ["iPhone 15", "Galaxy S24"]),
        ],
    )
    def test_orderings(self, catalog, ordering, expected):
        assert names(ProductQuery(ordering=ordering))[: len(expected)] == expected

    def test_pagination(self, catalog):
        query = ProductQuery(page=2, page_size=3, ordering=ProductOrdering.NAME)

        page = PostgresSearch().search(query)

        assert page.total == 4
        assert len(page.ids) == 1

    def test_facets(self, catalog):
        facets = PostgresSearch().facets(ProductQuery(category="smartphones"))

        assert {facet.value: facet.count for facet in facets.categories} == {
            "smartphones": 2,
            "audio": 1,
            "chargeurs": 1,
        }
        assert facets.min_price == Decimal("749.00")
        assert facets.max_price == Decimal("799.00")
        assert (facets.in_stock, facets.out_of_stock, facets.on_sale) == (1, 1, 1)


class TestAutocomplete:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [("iph", "iphone"), ("gal s2", "galaxy"), ("écout", "casque"), ("ecout", "casque")],
    )
    def test_prefix_matching(self, catalog, text, expected):
        assert PostgresSearch().suggest(text, limit=5) == (catalog[expected].pk,)

    def test_punctuation_only_gives_nothing(self, catalog):
        assert PostgresSearch().suggest("!!!", limit=5) == ()


class TestIndex:
    def test_remove_clears_the_vector(self, catalog):
        PostgresSearchIndex().remove([catalog["iphone"].pk])

        assert PostgresSearch().search(ProductQuery(text="iphone")).total == 0

    def test_related_products_share_the_category(self, catalog):
        related = SameCategoryRelated().related(catalog["iphone"].pk, limit=8)

        assert related == (catalog["galaxy"].pk,)

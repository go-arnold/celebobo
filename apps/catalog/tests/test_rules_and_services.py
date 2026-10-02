from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.catalog.domain.enums import Badge
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import FacetCount, Facets, SearchPage
from apps.catalog.domain.rules import (
    care_items,
    current_price,
    discount_percent,
    displayed_badge,
    rating_distribution,
)
from apps.catalog.services.search import CatalogSearchService

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)


class TestRules:
    @pytest.mark.parametrize(
        ("price", "sale", "expected"),
        [("899", None, "899"), ("899", "749", "749"), ("899", "950", "899")],
    )
    def test_current_price(self, price, sale, expected):
        assert current_price(Decimal(price), Decimal(sale) if sale else None) == Decimal(expected)

    def test_discount_percent(self):
        assert discount_percent(Decimal(899), Decimal(749)) == Decimal("16.69")
        assert discount_percent(Decimal(899), None) is None
        assert discount_percent(Decimal(100), Decimal(100)) is None

    def test_recent_products_are_new_whatever_their_badge(self):
        recent = NOW - timedelta(days=5)
        old = NOW - timedelta(days=30)

        assert displayed_badge(Badge.BEST_SELLER, recent, now=NOW, new_for_days=20) is Badge.NEW
        assert (
            displayed_badge(Badge.BEST_SELLER, old, now=NOW, new_for_days=20) is Badge.BEST_SELLER
        )
        assert displayed_badge(None, old, now=NOW, new_for_days=20) is None

    def test_care_items(self):
        assert care_items("Nettoyer à sec;\n Éviter l'eau ;; \n") == (
            "Nettoyer à sec",
            "Éviter l'eau",
        )

    def test_rating_distribution_always_has_five_buckets(self):
        assert rating_distribution({5: 3, 1: 1}) == {5: 3, 4: 0, 3: 0, 2: 0, 1: 1}


class StubEngine:
    def __init__(self) -> None:
        self.queries: list[ProductQuery] = []

    def search(self, query: ProductQuery) -> SearchPage:
        self.queries.append(query)
        return SearchPage(ids=(1, 2), total=2)

    def facets(self, query: ProductQuery) -> Facets:
        return Facets(
            categories=(
                FacetCount(value="smartphones", label="smartphones", count=4),
                FacetCount(value="audio", label="audio", count=0),
            ),
            min_price=Decimal(10),
            max_price=Decimal(900),
            in_stock=3,
            out_of_stock=1,
            on_sale=1,
        )

    def suggest(self, text: str, *, limit: int) -> tuple[int, ...]:
        return (9,)


def service(engine: StubEngine) -> CatalogSearchService:
    return CatalogSearchService(
        engine,
        category_names=lambda: {"smartphones": "Smartphones"},
        clock=lambda: NOW,
        new_for_days=20,
        max_page_size=48,
    )


class TestCatalogSearchService:
    def test_normalizes_queries(self):
        engine = StubEngine()

        service(engine).search(ProductQuery(text="  iphone   15 ", page=0, page_size=500))

        query = engine.queries[0]
        assert query.text == "iphone 15"
        assert query.page == 1
        assert query.page_size == 48

    def test_new_badge_becomes_a_date_threshold(self):
        engine = StubEngine()

        service(engine).search(ProductQuery(badge=Badge.NEW))

        assert engine.queries[0].new_since == NOW - timedelta(days=20)

    def test_facets_use_category_names_and_drop_empty_buckets(self):
        facets = service(StubEngine()).facets(ProductQuery())

        assert facets.categories == (FacetCount(value="smartphones", label="Smartphones", count=4),)

    def test_short_suggestions_skip_the_engine(self):
        assert service(StubEngine()).suggest(" a ", limit=6) == ()
        assert service(StubEngine()).suggest("ip", limit=6) == (9,)

    def test_blank_text_is_dropped(self):
        engine = StubEngine()

        service(engine).search(ProductQuery(text="   "))

        assert engine.queries[0].text is None

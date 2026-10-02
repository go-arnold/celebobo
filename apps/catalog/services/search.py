from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta

from apps.catalog.domain.enums import Badge
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import Facets, SearchPage
from apps.catalog.services.contracts import SearchEngine, SearchIndex
from core.registry import Registry

MIN_SUGGESTION_LENGTH = 2

search_engines: Registry[SearchEngine] = Registry("catalog search engine")
search_indexes: Registry[SearchIndex] = Registry("catalog search index")


class CatalogSearchService:
    def __init__(
        self,
        engine: SearchEngine,
        *,
        category_names: Callable[[], dict[str, str]],
        clock: Callable[[], datetime],
        new_for_days: int,
        max_page_size: int,
    ) -> None:
        self._engine = engine
        self._category_names = category_names
        self._clock = clock
        self._new_for_days = new_for_days
        self._max_page_size = max_page_size

    def search(self, query: ProductQuery) -> SearchPage:
        return self._engine.search(self.normalize(query))

    def facets(self, query: ProductQuery) -> Facets:
        facets = self._engine.facets(self.normalize(query))
        names = self._category_names()
        labelled = tuple(
            replace(facet, label=names.get(facet.value, facet.label))
            for facet in facets.categories
            if facet.count > 0
        )
        return replace(facets, categories=labelled)

    def suggest(self, text: str, *, limit: int) -> tuple[int, ...]:
        cleaned = " ".join(text.split())
        if len(cleaned) < MIN_SUGGESTION_LENGTH:
            return ()
        return self._engine.suggest(cleaned, limit=limit)

    def normalize(self, query: ProductQuery) -> ProductQuery:
        text = " ".join(query.text.split()) if query.text else None
        return replace(
            query,
            text=text or None,
            page=max(query.page, 1),
            page_size=min(max(query.page_size, 1), self._max_page_size),
            new_since=(
                self._clock() - timedelta(days=self._new_for_days)
                if query.badge is Badge.NEW
                else None
            ),
        )

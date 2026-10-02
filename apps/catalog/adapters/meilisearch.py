from collections.abc import Callable, Mapping, MutableMapping, Sequence
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Protocol

import meilisearch
from meilisearch.errors import MeilisearchError

from apps.catalog.conf import meilisearch_settings
from apps.catalog.domain.enums import Badge, ProductOrdering
from apps.catalog.domain.errors import SearchUnavailable
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import FacetCount, Facets, ProductDocument, SearchPage
from apps.catalog.services.search import search_engines, search_indexes

SORTS: Mapping[ProductOrdering, tuple[str, ...]] = MappingProxyType(
    {
        ProductOrdering.RELEVANCE: (),
        ProductOrdering.NEWEST: ("created_at:desc",),
        ProductOrdering.OLDEST: ("created_at:asc",),
        ProductOrdering.PRICE_ASC: ("current_price:asc",),
        ProductOrdering.PRICE_DESC: ("current_price:desc",),
        ProductOrdering.BEST_SELLING: ("sales_count:desc",),
        ProductOrdering.TOP_RATED: ("rating_avg:desc",),
        ProductOrdering.NAME: ("name_sort:asc",),
    }
)

INDEX_SETTINGS: Mapping[str, Any] = MappingProxyType(
    {
        "searchableAttributes": ["name", "category_name", "features", "description"],
        "filterableAttributes": [
            "id",
            "category_slug",
            "on_sale",
            "in_stock",
            "badge",
            "created_at",
            "current_price",
        ],
        "sortableAttributes": [
            "created_at",
            "current_price",
            "sales_count",
            "rating_avg",
            "name_sort",
        ],
        "pagination": {"maxTotalHits": 5000},
    }
)


class MeilisearchIndexHandle(Protocol):
    def search(self, query: str, opt_params: Mapping[str, Any] | None = None) -> dict[str, Any]: ...

    def update_settings(self, body: MutableMapping[str, Any]) -> Any: ...

    def add_documents(
        self, documents: Sequence[Mapping[str, Any]], primary_key: str | None = None
    ) -> Any: ...

    def delete_documents(self, ids: list[str | int] | None = None) -> Any: ...


def default_index() -> MeilisearchIndexHandle:
    settings = meilisearch_settings()
    client = meilisearch.Client(settings.url, settings.api_key or None, timeout=settings.timeout)
    index: MeilisearchIndexHandle = client.index(settings.index)
    return index


@search_engines.register("meilisearch")
class MeilisearchSearch:
    def __init__(self, index: Callable[[], MeilisearchIndexHandle] = default_index) -> None:
        self._index = index

    def search(self, query: ProductQuery) -> SearchPage:
        result = self._query(
            query.text or "",
            {
                "filter": filters(query),
                "sort": list(SORTS[query.effective_ordering]),
                "page": query.page,
                "hitsPerPage": query.page_size,
                "attributesToRetrieve": ["id"],
            },
        )
        ids = tuple(int(hit["id"]) for hit in result.get("hits", []))
        return SearchPage(ids=ids, total=int(result.get("totalHits", len(ids))))

    def facets(self, query: ProductQuery) -> Facets:
        scoped = self._facet_query(query, ["in_stock", "on_sale", "current_price"])
        by_category = self._facet_query(query.without_category(), ["category_slug"])
        distribution = scoped.get("facetDistribution", {})
        stats = scoped.get("facetStats", {}).get("current_price", {})
        stock = distribution.get("in_stock", {})
        return Facets(
            categories=tuple(
                FacetCount(value=slug, label=slug, count=int(count))
                for slug, count in by_category.get("facetDistribution", {})
                .get("category_slug", {})
                .items()
            ),
            min_price=_decimal(stats.get("min")),
            max_price=_decimal(stats.get("max")),
            in_stock=int(stock.get("true", 0)),
            out_of_stock=int(stock.get("false", 0)),
            on_sale=int(distribution.get("on_sale", {}).get("true", 0)),
        )

    def suggest(self, text: str, *, limit: int) -> tuple[int, ...]:
        result = self._query(text, {"limit": limit, "attributesToRetrieve": ["id"]})
        return tuple(int(hit["id"]) for hit in result.get("hits", []))

    def _facet_query(self, query: ProductQuery, facets: list[str]) -> dict[str, Any]:
        return self._query(
            query.text or "", {"filter": filters(query), "facets": facets, "limit": 0}
        )

    def _query(self, text: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._index().search(text, params)
        except MeilisearchError as exc:
            raise SearchUnavailable from exc


@search_indexes.register("meilisearch")
class MeilisearchIndex:
    def __init__(self, index: Callable[[], MeilisearchIndexHandle] = default_index) -> None:
        self._index = index

    def configure(self) -> None:
        self._call(lambda handle: handle.update_settings(dict(INDEX_SETTINGS)))

    def upsert(self, documents: Sequence[ProductDocument]) -> None:
        self._call(lambda handle: handle.add_documents(list(documents), primary_key="id"))

    def remove(self, product_ids: Sequence[int]) -> None:
        self._call(lambda handle: handle.delete_documents([*product_ids]))

    def _call(self, operation: Callable[[MeilisearchIndexHandle], Any]) -> None:
        try:
            operation(self._index())
        except MeilisearchError as exc:
            raise SearchUnavailable from exc


def filters(query: ProductQuery) -> list[str]:
    clauses: list[str] = []
    if query.category:
        clauses.append(f"category_slug = {_quoted(query.category)}")
    if query.ids:
        clauses.append(f"id IN [{', '.join(str(int(pk)) for pk in query.ids)}]")
    if query.on_sale is not None:
        clauses.append(f"on_sale = {str(query.on_sale).lower()}")
    if query.in_stock is not None:
        clauses.append(f"in_stock = {str(query.in_stock).lower()}")
    if query.badge is Badge.BEST_SELLER:
        clauses.append(f"badge = {_quoted(Badge.BEST_SELLER.value)}")
    if query.new_since is not None:
        clauses.append(f"created_at >= {int(query.new_since.timestamp())}")
    if query.min_price is not None:
        clauses.append(f"current_price >= {float(query.min_price)}")
    if query.max_price is not None:
        clauses.append(f"current_price <= {float(query.max_price)}")
    return clauses


def _quoted(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))

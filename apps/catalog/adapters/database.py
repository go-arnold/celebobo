from collections.abc import Sequence
from types import MappingProxyType

from django.db.models import (
    Case,
    Count,
    Exists,
    IntegerField,
    Max,
    Min,
    OuterRef,
    Q,
    QuerySet,
    When,
)

from apps.catalog.domain.enums import Badge, ProductOrdering
from apps.catalog.domain.queries import ProductQuery
from apps.catalog.domain.read_models import FacetCount, Facets, ProductDocument, SearchPage
from apps.catalog.models import Product, ProductFeature, visible_products
from apps.catalog.services.search import search_engines, search_indexes

ORDERINGS = MappingProxyType(
    {
        ProductOrdering.NEWEST: ("-created_at", "-pk"),
        ProductOrdering.OLDEST: ("created_at", "pk"),
        ProductOrdering.PRICE_ASC: ("current_price", "pk"),
        ProductOrdering.PRICE_DESC: ("-current_price", "-pk"),
        ProductOrdering.BEST_SELLING: ("-sales_count", "-pk"),
        ProductOrdering.TOP_RATED: ("-rating_avg", "-reviews_count", "-pk"),
        ProductOrdering.NAME: ("name", "pk"),
    }
)


@search_engines.register("database")
class DatabaseSearch:
    def search(self, query: ProductQuery) -> SearchPage:
        products = filtered(query)
        ordered = _ordered(products, query)
        ids = ordered.values_list("pk", flat=True)[query.offset : query.offset + query.page_size]
        return SearchPage(ids=tuple(ids), total=products.count())

    def facets(self, query: ProductQuery) -> Facets:
        products = filtered(query)
        categories = (
            filtered(query.without_category())
            .values("category__slug", "category__name")
            .annotate(total=Count("pk"))
            .order_by("-total", "category__name")
        )
        prices = products.aggregate(low=Min("current_price"), high=Max("current_price"))
        total = products.count()
        in_stock = products.filter(stock__gt=0).count()
        return Facets(
            categories=tuple(
                FacetCount(
                    value=row["category__slug"], label=row["category__name"], count=row["total"]
                )
                for row in categories
            ),
            min_price=prices["low"],
            max_price=prices["high"],
            in_stock=in_stock,
            out_of_stock=total - in_stock,
            on_sale=products.filter(sale_price__isnull=False).count(),
        )

    def suggest(self, text: str, *, limit: int) -> tuple[int, ...]:
        query = ProductQuery(text=text, ordering=ProductOrdering.RELEVANCE)
        return tuple(_ordered(filtered(query), query).values_list("pk", flat=True)[:limit])


@search_indexes.register("null")
class NullIndex:
    def configure(self) -> None:
        return None

    def upsert(self, documents: Sequence[ProductDocument]) -> None:
        return None

    def remove(self, product_ids: Sequence[int]) -> None:
        return None


class SameCategoryRelated:
    def related(self, product_id: int, *, limit: int) -> tuple[int, ...]:
        category_id = (
            Product.objects.filter(pk=product_id).values_list("category_id", flat=True).first()
        )
        if category_id is None:
            return ()
        return tuple(
            visible_products()
            .filter(category_id=category_id)
            .exclude(pk=product_id)
            .order_by("-sales_count", "-rating_avg", "-pk")
            .values_list("pk", flat=True)[:limit]
        )


class NoPurchaseHistory:
    def has_received(self, user_id: int, product_id: int) -> bool:
        return False


def filtered(query: ProductQuery) -> QuerySet[Product]:
    products = visible_products()
    for term in (query.text or "").split():
        products = products.filter(
            Q(name__icontains=term)
            | Q(description__icontains=term)
            | Q(category__name__icontains=term)
            | Exists(ProductFeature.objects.filter(product=OuterRef("pk"), name__icontains=term))
        )
    if query.category:
        products = products.filter(category__slug=query.category)
    if query.ids:
        products = products.filter(pk__in=query.ids)
    if query.on_sale is not None:
        products = products.filter(sale_price__isnull=not query.on_sale)
    if query.in_stock is not None:
        products = products.filter(stock__gt=0) if query.in_stock else products.filter(stock=0)
    if query.badge is Badge.BEST_SELLER:
        products = products.filter(badge=Badge.BEST_SELLER.value)
    if query.new_since is not None:
        products = products.filter(created_at__gte=query.new_since)
    if query.min_price is not None:
        products = products.filter(current_price__gte=query.min_price)
    if query.max_price is not None:
        products = products.filter(current_price__lte=query.max_price)
    return products


def _ordered(products: QuerySet[Product], query: ProductQuery) -> QuerySet[Product]:
    ordering = query.effective_ordering
    if ordering is not ProductOrdering.RELEVANCE:
        return products.order_by(*ORDERINGS[ordering])
    if not query.text:
        return products.order_by(*ORDERINGS[ProductOrdering.NEWEST])
    return products.annotate(
        relevance=Case(
            When(name__istartswith=query.text, then=0),
            When(name__icontains=query.text, then=1),
            default=2,
            output_field=IntegerField(),
        )
    ).order_by("relevance", "-sales_count", "-pk")

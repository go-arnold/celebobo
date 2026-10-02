from collections.abc import Iterator, Sequence
from datetime import datetime
from decimal import Decimal

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus
from apps.catalog.domain.errors import CategoryNotFound, ProductNotFound
from apps.catalog.domain.read_models import (
    CategoryRef,
    CategoryView,
    OptionView,
    ProductCard,
    ProductDetail,
    ProductDocument,
    ReviewAuthor,
    ReviewSummary,
    ReviewView,
    VariantView,
)
from apps.catalog.domain.rules import (
    care_items,
    discount_percent,
    displayed_badge,
    rating_distribution,
)
from apps.catalog.models import (
    Category,
    Favorite,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    visible_products,
)


class CategorySelector:
    def active(self) -> list[CategoryView]:
        return [_category_view(category) for category in self._annotated()]

    def by_slug(self, slug: str) -> CategoryView:
        category = self._annotated().filter(slug=slug).first()
        if category is None:
            raise CategoryNotFound
        return _category_view(category)

    def names(self) -> dict[str, str]:
        return dict(Category.objects.filter(is_active=True).values_list("slug", "name"))

    @staticmethod
    def _annotated() -> QuerySet[Category]:
        visible = Q(products__is_active=True, products__deleted=None)
        categories: QuerySet[Category] = Category.objects.filter(is_active=True).annotate(
            products_count=Count("products", filter=visible, distinct=True)
        )
        return categories


class ProductCardSelector:
    def __init__(self, *, now: datetime, new_for_days: int) -> None:
        self._now = now
        self._new_for_days = new_for_days

    def cards(self, ids: Sequence[int]) -> list[ProductCard]:
        products = {
            product.pk: product
            for product in visible_products()
            .filter(pk__in=ids)
            .select_related("category")
            .prefetch_related(_first_images())
        }
        return [self.card(products[pk]) for pk in ids if pk in products]

    def card(self, product: Product) -> ProductCard:
        images = getattr(product, "ordered_images", None) or list(product.images.all()[:1])
        return ProductCard(
            id=product.pk,
            slug=product.slug,
            name=product.name,
            description=product.description,
            category=CategoryRef(
                id=product.category.pk, slug=product.category.slug, name=product.category.name
            ),
            image=images[0].url if images else "",
            price=product.price,
            sale_price=product.sale_price,
            current_price=product.current_price,
            discount_percent=discount_percent(product.price, product.sale_price),
            badge=displayed_badge(
                Badge(product.badge) if product.badge else None,
                product.created_at,
                now=self._now,
                new_for_days=self._new_for_days,
            ),
            rating=product.rating_avg,
            reviews_count=product.reviews_count,
            in_stock=product.in_stock,
            free_shipping=product.free_shipping,
        )


class ProductDetailSelector:
    def __init__(self, cards: ProductCardSelector) -> None:
        self._cards = cards

    def by_slug(self, slug: str) -> ProductDetail:
        product = (
            visible_products()
            .filter(slug=slug)
            .select_related("category")
            .prefetch_related(
                "images",
                "features",
                "options",
                Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True)),
            )
            .first()
        )
        if product is None:
            raise ProductNotFound
        images = list(product.images.all())
        return ProductDetail(
            card=self._cards.card(product),
            long_description=product.long_description,
            images=tuple(image.url for image in images),
            features=tuple(feature.name for feature in product.features.all()),
            care_instructions=care_items(product.care_instructions),
            delivery_policy_primary=product.delivery_policy_primary,
            delivery_policy_secondary=product.delivery_policy_secondary,
            shipping_fee=product.shipping_fee,
            low_stock=0 < product.stock <= product.stock_threshold,
            options=tuple(
                OptionView(name=option.name, values=tuple(option.values))
                for option in product.options.all()
            ),
            variants=tuple(
                VariantView(
                    id=variant.pk,
                    sku=variant.sku,
                    label=variant.label,
                    attributes=dict(variant.attributes),
                    price=variant.price if variant.price is not None else product.current_price,
                    in_stock=variant.stock > 0,
                    stock=variant.stock,
                    image=variant.image,
                )
                for variant in product.variants.all()
            ),
        )

    def id_for(self, slug: str) -> int:
        product_id = visible_products().filter(slug=slug).values_list("pk", flat=True).first()
        if product_id is None:
            raise ProductNotFound
        return product_id


class ProductDocumentSelector:
    def documents(self, ids: Sequence[int]) -> list[ProductDocument]:
        products = (
            visible_products()
            .filter(pk__in=ids)
            .select_related("category")
            .prefetch_related("features")
        )
        return [_document(product) for product in products]

    def ids_in_category(self, category_id: int) -> list[int]:
        return list(
            Product.all_objects.filter(category_id=category_id).values_list("pk", flat=True)
        )

    def all_ids(self, *, batch_size: int = 500) -> Iterator[list[int]]:
        ids = list(Product.all_objects.order_by("pk").values_list("pk", flat=True))
        for start in range(0, len(ids), batch_size):
            yield ids[start : start + batch_size]


class ReviewSelector:
    def page(self, product_id: int, *, offset: int, limit: int) -> tuple[list[ReviewView], int]:
        queryset = self._published(product_id)
        reviews = queryset.select_related("user")[offset : offset + limit]
        return [to_review_view(review) for review in reviews], queryset.count()

    def summary(self, product_id: int) -> ReviewSummary:
        counts = dict(
            self._published(product_id)
            .values_list("rating")
            .annotate(total=Count("pk"))
            .values_list("rating", "total")
        )
        total = sum(counts.values())
        average = (
            Decimal(sum(stars * count for stars, count in counts.items()) / total).quantize(
                Decimal("0.01")
            )
            if total
            else Decimal("0.00")
        )
        return ReviewSummary(average=average, count=total, distribution=rating_distribution(counts))

    @staticmethod
    def _published(product_id: int) -> QuerySet[Review]:
        return Review.objects.filter(product_id=product_id, status=ReviewStatus.PUBLISHED.value)


class FavoriteSelector:
    def favorite_ids(self, user_id: int, product_ids: Sequence[int]) -> frozenset[int]:
        return frozenset(
            Favorite.objects.filter(user_id=user_id, product_id__in=product_ids).values_list(
                "product_id", flat=True
            )
        )

    def page(self, user_id: int, *, offset: int, limit: int) -> tuple[tuple[int, ...], int]:
        queryset = Favorite.objects.filter(user_id=user_id, product__in=visible_products())
        ids = tuple(queryset.values_list("product_id", flat=True)[offset : offset + limit])
        return ids, queryset.count()


def _first_images() -> Prefetch[str, QuerySet[ProductImage], str]:
    return Prefetch(
        "images", queryset=ProductImage.objects.order_by("position"), to_attr="ordered_images"
    )


def _category_view(category: Category) -> CategoryView:
    return CategoryView(
        id=category.pk,
        slug=category.slug,
        name=category.name,
        description=category.description,
        image=category.image,
        icon=CategoryIcon(category.icon),
        products_count=getattr(category, "products_count", 0),
    )


def _document(product: Product) -> ProductDocument:
    return {
        "id": product.pk,
        "name": product.name,
        "name_sort": product.name.lower(),
        "description": product.description,
        "category_id": product.category.pk,
        "category_slug": product.category.slug,
        "category_name": product.category.name,
        "features": [feature.name for feature in product.features.all()],
        "current_price": float(product.current_price),
        "on_sale": product.sale_price is not None,
        "in_stock": product.in_stock,
        "badge": product.badge or None,
        "created_at": int(product.created_at.timestamp()),
        "sales_count": product.sales_count,
        "rating_avg": float(product.rating_avg),
    }


def to_review_view(review: Review) -> ReviewView:
    user = review.user
    first_name = getattr(user, "first_name", "")
    last_name = getattr(user, "last_name", "")
    name = f"{first_name} {last_name[:1]}.".strip() if last_name else first_name
    return ReviewView(
        id=review.pk,
        rating=review.rating,
        message=review.message,
        verified=review.verified,
        author=ReviewAuthor(id=user.pk, name=name or "Client", avatar=getattr(user, "avatar", "")),
        created_at=review.created_at,
    )

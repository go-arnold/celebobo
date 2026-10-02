from collections.abc import Iterator, Sequence
from datetime import datetime
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Prefetch,
    Q,
    QuerySet,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce

from apps.catalog.domain.backoffice import (
    AdminCategory,
    AdminImage,
    AdminProductDetail,
    AdminProductRow,
    AdminReview,
    AdminVariant,
    LowStockItem,
    ProductRef,
    ProductStats,
    StockMovementView,
)
from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus, StockReason
from apps.catalog.domain.errors import CategoryNotFound, ProductNotFound, ReviewNotFound
from apps.catalog.domain.management import BackofficeProductFilters, ProductStatus, ReviewFilters
from apps.catalog.domain.management_rules import margin
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
    StockMovement,
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


class AdminProductSelector:
    def page(
        self, filters: BackofficeProductFilters, *, offset: int, limit: int
    ) -> tuple[list[AdminProductRow], int, ProductStats]:
        products = _admin_filtered(filters)
        rows = list(
            products.select_related("category")
            .prefetch_related(_first_images())
            .annotate(variants_count=Count("variants", distinct=True))
            .order_by("-updated_at", "-pk")[offset : offset + limit]
        )
        return [_admin_row(product) for product in rows], products.count(), self.stats()

    def detail(self, product_id: int) -> AdminProductDetail:
        product = (
            Product.all_objects.select_related("category")
            .prefetch_related("images", "features", "options", "variants")
            .annotate(variants_count=Count("variants", distinct=True))
            .filter(pk=product_id)
            .first()
        )
        if product is None:
            raise ProductNotFound
        images = list(product.images.all())
        return AdminProductDetail(
            row=_admin_row(product, images[:1]),
            description=product.description,
            long_description=product.long_description,
            care_instructions=product.care_instructions,
            delivery_policy_primary=product.delivery_policy_primary,
            delivery_policy_secondary=product.delivery_policy_secondary,
            free_shipping=product.free_shipping,
            shipping_fee=product.shipping_fee,
            sell_by=product.sell_by,
            features=tuple(feature.name for feature in product.features.all()),
            options=tuple(
                OptionView(name=option.name, values=tuple(option.values))
                for option in product.options.all()
            ),
            images=tuple(AdminImage(url=image.url, position=image.position) for image in images),
            variants=tuple(
                AdminVariant(
                    id=variant.pk,
                    sku=variant.sku,
                    label=variant.label,
                    attributes=dict(variant.attributes),
                    price=variant.price,
                    stock=variant.stock,
                    image=variant.image,
                    is_active=variant.is_active,
                )
                for variant in product.variants.all()
            ),
        )

    def stats(self) -> ProductStats:
        live = Product.objects.all()
        low = live.filter(stock__gt=0, stock__lte=F("stock_threshold"))
        value = live.aggregate(
            total=Sum(
                ExpressionWrapper(
                    F("stock") * Coalesce("cost_price", Value(Decimal(0))),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            )
        )["total"]
        return ProductStats(
            total=live.count(),
            active=live.filter(is_active=True).count(),
            on_sale=live.filter(sale_price__isnull=False).count(),
            out_of_stock=live.filter(stock=0).count(),
            low_stock=low.count(),
            stock_value=Decimal(value or 0).quantize(Decimal("0.01")),
            trashed=Product.deleted_objects.count(),
        )


class StockSelector:
    def movements(
        self, product_id: int, *, offset: int, limit: int
    ) -> tuple[list[StockMovementView], int]:
        movements = StockMovement.objects.filter(product_id=product_id)
        page = movements.select_related("actor").order_by("-created_at", "-pk")[
            offset : offset + limit
        ]
        return [_movement_view(movement) for movement in page], movements.count()

    def alerts(self, *, limit: int = 100) -> list[LowStockItem]:
        items: list[LowStockItem] = []
        products = (
            Product.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True))
            )
            .order_by("stock", "name")
        )
        for product in products:
            variants = list(product.variants.all())
            if variants:
                items.extend(
                    LowStockItem(
                        product_id=product.pk,
                        variant_id=variant.pk,
                        name=product.name,
                        variant_label=variant.label,
                        stock=variant.stock,
                        threshold=product.stock_threshold,
                    )
                    for variant in variants
                    if variant.stock <= product.stock_threshold
                )
            elif product.stock <= product.stock_threshold:
                items.append(
                    LowStockItem(
                        product_id=product.pk,
                        variant_id=None,
                        name=product.name,
                        variant_label="",
                        stock=product.stock,
                        threshold=product.stock_threshold,
                    )
                )
            if len(items) >= limit:
                break
        return sorted(items, key=lambda item: (item.stock, item.name))[:limit]

    def movement(self, movement_id: int) -> StockMovementView:
        return _movement_view(StockMovement.objects.select_related("actor").get(pk=movement_id))


class AdminCategorySelector:
    def all(self) -> list[AdminCategory]:
        categories = Category.objects.annotate(
            products_count=Count("products", filter=Q(products__deleted=None), distinct=True)
        ).order_by("position", "name")
        return [_admin_category(category) for category in categories]

    def one(self, category_id: int) -> AdminCategory:
        category = (
            Category.objects.annotate(
                products_count=Count("products", filter=Q(products__deleted=None), distinct=True)
            )
            .filter(pk=category_id)
            .first()
        )
        if category is None:
            raise CategoryNotFound
        return _admin_category(category)


class AdminReviewSelector:
    def page(
        self, filters: ReviewFilters, *, offset: int, limit: int
    ) -> tuple[list[AdminReview], int]:
        reviews = Review.objects.select_related("product", "user")
        if filters.status is not None:
            reviews = reviews.filter(status=filters.status.value)
        if filters.product_id is not None:
            reviews = reviews.filter(product_id=filters.product_id)
        if filters.rating is not None:
            reviews = reviews.filter(rating=filters.rating)
        if filters.search:
            reviews = reviews.filter(
                Q(message__icontains=filters.search) | Q(product__name__icontains=filters.search)
            )
        page = reviews.order_by("-created_at", "-pk")[offset : offset + limit]
        return [_admin_review(review) for review in page], reviews.count()

    def one(self, review_id: int) -> AdminReview:
        review = Review.objects.select_related("product", "user").filter(pk=review_id).first()
        if review is None:
            raise ReviewNotFound
        return _admin_review(review)


def _admin_filtered(filters: BackofficeProductFilters) -> QuerySet[Product]:
    sources = {
        ProductStatus.ACTIVE: Product.objects.filter(is_active=True),
        ProductStatus.INACTIVE: Product.objects.filter(is_active=False),
        ProductStatus.TRASH: Product.deleted_objects.all(),
        ProductStatus.ALL: Product.objects.all(),
    }
    products: QuerySet[Product] = sources[filters.status]
    if filters.search:
        term = filters.search.strip()
        products = products.filter(
            Q(name__icontains=term)
            | Q(slug__icontains=term)
            | Q(variants__sku__iexact=term)
            | Q(description__icontains=term)
        ).distinct()
    if filters.category_id is not None:
        products = products.filter(category_id=filters.category_id)
    if filters.on_sale is not None:
        products = products.filter(sale_price__isnull=not filters.on_sale)
    if filters.out_of_stock:
        products = products.filter(stock=0)
    if filters.low_stock:
        products = products.filter(stock__gt=0, stock__lte=F("stock_threshold"))
    if filters.badge is not None:
        products = products.filter(badge=filters.badge.value)
    if filters.min_price is not None:
        products = products.filter(current_price__gte=filters.min_price)
    if filters.max_price is not None:
        products = products.filter(current_price__lte=filters.max_price)
    return products


def _admin_row(product: Product, images: Sequence[ProductImage] | None = None) -> AdminProductRow:
    first = images if images is not None else getattr(product, "ordered_images", [])
    amount, percent = margin(product.current_price, product.cost_price)
    status = (
        ProductStatus.TRASH
        if product.is_trashed
        else ProductStatus.ACTIVE
        if product.is_active
        else ProductStatus.INACTIVE
    )
    return AdminProductRow(
        id=product.pk,
        slug=product.slug,
        name=product.name,
        category=CategoryRef(
            id=product.category.pk, slug=product.category.slug, name=product.category.name
        ),
        image=first[0].url if first else "",
        price=product.price,
        sale_price=product.sale_price,
        cost_price=product.cost_price,
        current_price=product.current_price,
        margin=amount,
        margin_percent=percent,
        stock=product.stock,
        stock_threshold=product.stock_threshold,
        low_stock=0 < product.stock <= product.stock_threshold,
        status=status,
        badge=Badge(product.badge) if product.badge else None,
        variants_count=getattr(product, "variants_count", 0),
        sales_count=product.sales_count,
        rating=product.rating_avg,
        updated_at=product.updated_at,
    )


def _movement_view(movement: StockMovement) -> StockMovementView:
    actor = movement.actor
    return StockMovementView(
        id=movement.pk,
        product_id=movement.product_id,
        variant_id=movement.variant_id,
        delta=movement.delta,
        balance_after=movement.balance_after,
        reason=StockReason(movement.reason),
        note=movement.note,
        actor_name=(
            f"{getattr(actor, 'first_name', '')} {getattr(actor, 'last_name', '')}".strip()
            or getattr(actor, "email", None)
        )
        if actor
        else None,
        source_type=movement.source_type,
        source_id=movement.source_id,
        created_at=movement.created_at,
    )


def _admin_category(category: Category) -> AdminCategory:
    return AdminCategory(
        id=category.pk,
        slug=category.slug,
        name=category.name,
        description=category.description,
        image=category.image,
        icon=CategoryIcon(category.icon),
        is_active=category.is_active,
        position=category.position,
        products_count=getattr(category, "products_count", 0),
    )


def _admin_review(review: Review) -> AdminReview:
    view = to_review_view(review)
    return AdminReview(
        id=review.pk,
        product=ProductRef(
            id=review.product.pk, slug=review.product.slug, name=review.product.name
        ),
        author=view.author,
        rating=review.rating,
        message=review.message,
        status=ReviewStatus(review.status),
        verified=review.verified,
        created_at=review.created_at,
    )

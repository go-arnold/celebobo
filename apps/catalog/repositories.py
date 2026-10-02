from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from django.db.models import Avg, Count, Max, Model, Prefetch, QuerySet, Sum

from apps.catalog.domain.enums import ReviewStatus, StockReason
from apps.catalog.domain.management import OptionInput
from apps.catalog.domain.queries import StockSource
from apps.catalog.models import (
    Category,
    Favorite,
    Product,
    ProductFeature,
    ProductImage,
    ProductOption,
    ProductVariant,
    Review,
    StockMovement,
    visible_products,
)


class ProductRepository:
    def visible(self, product_id: int) -> Product | None:
        return visible_products().filter(pk=product_id).first()

    def visible_by_slug(self, slug: str) -> Product | None:
        return visible_products().filter(slug=slug).first()

    def refresh_rating(self, product_id: int) -> None:
        aggregates = Review.objects.filter(
            product_id=product_id, status=ReviewStatus.PUBLISHED.value
        ).aggregate(average=Avg("rating"), total=Count("pk"))
        average = Decimal(str(aggregates["average"] or 0)).quantize(Decimal("0.01"))
        Product.all_objects.filter(pk=product_id).update(
            rating_avg=average, reviews_count=aggregates["total"]
        )


class ReviewRepository:
    def for_user(self, product_id: int, user_id: int) -> Review | None:
        return Review.objects.filter(product_id=product_id, user_id=user_id).first()

    def upsert(
        self, *, product_id: int, user_id: int, rating: int, message: str, verified: bool
    ) -> tuple[Review, bool]:
        return Review.objects.update_or_create(
            product_id=product_id,
            user_id=user_id,
            defaults={
                "rating": rating,
                "message": message,
                "verified": verified,
                "status": ReviewStatus.PUBLISHED.value,
            },
        )


class FavoriteRepository:
    def add(self, user_id: int, product_id: int) -> bool:
        _, created = Favorite.objects.get_or_create(user_id=user_id, product_id=product_id)
        return created

    def remove(self, user_id: int, product_id: int) -> bool:
        deleted, _ = Favorite.objects.filter(user_id=user_id, product_id=product_id).delete()
        return deleted > 0


class StockRepository:
    def for_pricing(self, product_ids: Iterable[int]) -> dict[int, Product]:
        products = (
            visible_products()
            .filter(pk__in=set(product_ids))
            .prefetch_related(
                Prefetch("images", queryset=ProductImage.objects.order_by("position")),
                Prefetch("variants", queryset=ProductVariant.objects.filter(is_active=True)),
            )
        )
        return {product.pk: product for product in products}

    def lock(
        self, product_ids: Iterable[int], variant_ids: Iterable[int], *, visible_only: bool
    ) -> tuple[dict[int, Product], dict[int, ProductVariant]]:
        source = visible_products() if visible_only else Product.all_objects.all()
        products = source.select_for_update(of=("self",)).filter(pk__in=set(product_ids))
        variants = ProductVariant.objects.select_for_update().filter(pk__in=set(variant_ids))
        return (
            {product.pk: product for product in products.order_by("pk")},
            {variant.pk: variant for variant in variants.order_by("pk")},
        )

    def products_with_variants(self, product_ids: Iterable[int]) -> set[int]:
        return set(
            ProductVariant.objects.filter(product_id__in=set(product_ids), is_active=True)
            .values_list("product_id", flat=True)
            .distinct()
        )

    def move(
        self,
        product: Product,
        variant: ProductVariant | None,
        *,
        delta: int,
        reason: StockReason,
        source: StockSource,
        note: str = "",
    ) -> StockMovement:
        product.stock += delta
        product.save(update_fields=["stock", "updated_at"])
        if variant is not None:
            variant.stock += delta
            variant.save(update_fields=["stock"])
        return StockMovement.objects.create(
            product=product,
            variant=variant,
            delta=delta,
            balance_after=variant.stock if variant is not None else product.stock,
            reason=reason.value,
            note=note,
            actor_id=source.actor_id,
            source_type=source.kind,
            source_id=source.id,
        )

    def low_levels(self, product_ids: Iterable[int]) -> list[tuple[int, int | None, int, int]]:
        products = Product.all_objects.filter(pk__in=set(product_ids))
        levels: list[tuple[int, int | None, int, int]] = []
        for product in products.prefetch_related("variants"):
            variants = [variant for variant in product.variants.all() if variant.is_active]
            if variants:
                levels.extend(
                    (product.pk, variant.pk, variant.stock, product.stock_threshold)
                    for variant in variants
                    if variant.stock <= product.stock_threshold
                )
            elif product.stock <= product.stock_threshold:
                levels.append((product.pk, None, product.stock, product.stock_threshold))
        return levels


class ProductAdminRepository:
    def get(self, product_id: int, *, for_update: bool = False) -> Product | None:
        products = Product.all_objects.all()
        if for_update:
            products = products.select_for_update(of=("self",))
        return products.filter(pk=product_id).first()

    def create(self, **fields: Any) -> Product:
        product: Product = Product.objects.create(**fields)
        return product

    def save(self, product: Product, *, fields: Iterable[str]) -> None:
        product.save(update_fields=[*fields, "updated_at"])

    def slug_taken(self, slug: str, *, exclude_id: int | None = None) -> bool:
        return _excluding(Product.all_objects.filter(slug=slug), exclude_id).exists()

    def replace_features(self, product: Product, names: Sequence[str]) -> None:
        product.features.all().delete()
        ProductFeature.objects.bulk_create(
            ProductFeature(product=product, name=name, position=index)
            for index, name in enumerate(names)
        )

    def replace_options(self, product: Product, options: Sequence[OptionInput]) -> None:
        product.options.all().delete()
        ProductOption.objects.bulk_create(
            ProductOption(
                product=product, name=option.name, values=list(option.values), position=index
            )
            for index, option in enumerate(options)
        )

    def replace_images(self, product: Product, urls: Sequence[str]) -> None:
        product.images.all().delete()
        ProductImage.objects.bulk_create(
            ProductImage(product=product, url=url, position=index) for index, url in enumerate(urls)
        )

    def options(self, product: Product) -> dict[str, list[str]]:
        return {option.name: list(option.values) for option in product.options.all()}

    def features(self, product: Product) -> list[str]:
        return list(product.features.values_list("name", flat=True))

    def image_urls(self, product: Product) -> list[str]:
        return list(product.images.values_list("url", flat=True))

    def variants(self, product: Product) -> list[ProductVariant]:
        return list(product.variants.all())

    def variant(self, variant_id: int, *, for_update: bool = False) -> ProductVariant | None:
        variants = (
            ProductVariant.objects.select_for_update() if for_update else ProductVariant.objects
        )
        return variants.filter(pk=variant_id).first()

    def sku_taken(self, sku: str, *, exclude_id: int | None = None) -> bool:
        return _excluding(ProductVariant.objects.filter(sku=sku), exclude_id).exists()

    def attributes_taken(
        self, product: Product, attributes: dict[str, str], *, exclude_id: int | None = None
    ) -> bool:
        return _excluding(product.variants.filter(attributes=attributes), exclude_id).exists()

    def create_variant(self, product: Product, **fields: Any) -> ProductVariant:
        return ProductVariant.objects.create(product=product, **fields)

    def save_variant(self, variant: ProductVariant, *, fields: Iterable[str]) -> None:
        variant.save(update_fields=[*fields])

    def delete_variant(self, variant: ProductVariant) -> bool:
        if StockMovement.objects.filter(variant=variant).exists():
            variant.is_active = False
            variant.save(update_fields=["is_active"])
            return False
        variant.delete()
        return True

    def recompute_stock(self, product: Product) -> int:
        total = product.variants.filter(is_active=True).aggregate(total=Sum("stock"))["total"]
        if total is not None or product.variants.exists():
            product.stock = int(total or 0)
            product.save(update_fields=["stock", "updated_at"])
        return product.stock

    def has_active_variants(self, product: Product) -> bool:
        return product.variants.filter(is_active=True).exists()

    def soft_delete(self, product: Product) -> None:
        product.delete()

    def restore(self, product: Product) -> None:
        product.undelete()

    def for_bulk(self, ids: Sequence[int]) -> list[Product]:
        return list(Product.all_objects.select_for_update(of=("self",)).filter(pk__in=list(ids)))


class CategoryAdminRepository:
    def get(self, category_id: int, *, for_update: bool = False) -> Category | None:
        categories = Category.objects.select_for_update() if for_update else Category.objects
        return categories.filter(pk=category_id).first()

    def create(self, **fields: Any) -> Category:
        category: Category = Category.objects.create(**fields)
        return category

    def save(self, category: Category, *, fields: Iterable[str]) -> None:
        category.save(update_fields=[*fields, "updated_at"])

    def name_taken(self, name: str, *, exclude_id: int | None = None) -> bool:
        return _excluding(Category.objects.filter(name__iexact=name), exclude_id).exists()

    def slug_taken(self, slug: str, *, exclude_id: int | None = None) -> bool:
        return _excluding(Category.all_objects.filter(slug=slug), exclude_id).exists()

    def products_count(self, category: Category) -> int:
        return Product.objects.filter(category=category).count()

    def move_products(self, source: Category, target: Category) -> list[int]:
        ids = list(Product.all_objects.filter(category=source).values_list("pk", flat=True))
        Product.all_objects.filter(pk__in=ids).update(category=target)
        return ids

    def soft_delete(self, category: Category) -> None:
        category.delete()

    def next_position(self) -> int:
        return int(Category.objects.aggregate(top=Max("position"))["top"] or 0) + 1

    def reorder(self, ids: Sequence[int]) -> None:
        for position, category_id in enumerate(ids, start=1):
            Category.objects.filter(pk=category_id).update(position=position)


class ReviewAdminRepository:
    def get(self, review_id: int, *, for_update: bool = False) -> Review | None:
        reviews = Review.objects.select_for_update() if for_update else Review.objects
        return reviews.filter(pk=review_id).first()

    def save(self, review: Review, *, fields: Iterable[str]) -> None:
        review.save(update_fields=[*fields, "updated_at"])


def _excluding[M: Model](queryset: QuerySet[M], pk: int | None) -> QuerySet[M]:
    return queryset if pk is None else queryset.exclude(pk=pk)

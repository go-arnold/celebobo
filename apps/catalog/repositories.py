from collections.abc import Iterable
from decimal import Decimal

from django.db.models import Avg, Count, Prefetch

from apps.catalog.domain.enums import ReviewStatus, StockReason
from apps.catalog.domain.queries import StockSource
from apps.catalog.models import (
    Favorite,
    Product,
    ProductImage,
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

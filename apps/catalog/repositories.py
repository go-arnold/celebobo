from decimal import Decimal

from django.db.models import Avg, Count

from apps.catalog.domain.enums import ReviewStatus
from apps.catalog.models import Favorite, Product, Review, visible_products


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

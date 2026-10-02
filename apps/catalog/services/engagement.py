from apps.catalog.domain.errors import ProductNotFound, ReviewNotAllowed
from apps.catalog.domain.queries import PostReview
from apps.catalog.domain.read_models import ReviewEligibility
from apps.catalog.models import Review
from apps.catalog.services.contracts import (
    FavoriteStore,
    ProductStore,
    PurchaseVerifier,
    ReviewStore,
)


class ReviewService:
    def __init__(
        self, products: ProductStore, reviews: ReviewStore, purchases: PurchaseVerifier
    ) -> None:
        self._products = products
        self._reviews = reviews
        self._purchases = purchases

    def eligibility(self, user_id: int, product_id: int) -> ReviewEligibility:
        existing = self._reviews.for_user(product_id, user_id)
        if not self._purchases.has_received(user_id, product_id):
            return ReviewEligibility(
                can_review=False,
                reason=ReviewNotAllowed.default_code,
                existing_review_id=existing.pk if existing else None,
            )
        return ReviewEligibility(
            can_review=True, existing_review_id=existing.pk if existing else None
        )

    def post(self, user_id: int, product_id: int, command: PostReview) -> tuple[Review, bool]:
        if self._products.visible(product_id) is None:
            raise ProductNotFound
        if not self._purchases.has_received(user_id, product_id):
            raise ReviewNotAllowed
        review, created = self._reviews.upsert(
            product_id=product_id,
            user_id=user_id,
            rating=command.rating,
            message=" ".join(command.message.split()),
            verified=True,
        )
        self._products.refresh_rating(product_id)
        return review, created


class FavoriteService:
    def __init__(self, favorites: FavoriteStore, products: ProductStore) -> None:
        self._favorites = favorites
        self._products = products

    def add(self, user_id: int, product_id: int) -> bool:
        if self._products.visible(product_id) is None:
            raise ProductNotFound
        return self._favorites.add(user_id, product_id)

    def remove(self, user_id: int, product_id: int) -> bool:
        return self._favorites.remove(user_id, product_id)

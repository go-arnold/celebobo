from core.events.base import DomainEvent, domain_event


@domain_event
class ProductChanged(DomainEvent):
    product_id: int

    @property
    def product_ids(self) -> tuple[int, ...]:
        return (self.product_id,)


@domain_event
class ProductRemoved(DomainEvent):
    product_id: int

    @property
    def product_ids(self) -> tuple[int, ...]:
        return (self.product_id,)


# one event for a whole bulk action, so handlers index and revalidate the batch at once
@domain_event
class ProductsChanged(DomainEvent):
    product_ids: tuple[int, ...]


@domain_event
class ProductsRemoved(DomainEvent):
    product_ids: tuple[int, ...]


@domain_event
class CategoryChanged(DomainEvent):
    category_id: int


@domain_event
class BrandChanged(DomainEvent):
    brand_id: int


@domain_event
class ReviewPosted(DomainEvent):
    product_id: int
    review_id: int
    rating: int
    created: bool


@domain_event
class FavoriteAdded(DomainEvent):
    user_id: int
    product_id: int


@domain_event
class FavoriteRemoved(DomainEvent):
    user_id: int
    product_id: int


@domain_event
class StockLow(DomainEvent):
    product_id: int
    variant_id: int | None
    stock: int
    threshold: int

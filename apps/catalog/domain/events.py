from core.events.base import DomainEvent, domain_event


@domain_event
class ProductChanged(DomainEvent):
    product_id: int


@domain_event
class ProductRemoved(DomainEvent):
    product_id: int


@domain_event
class CategoryChanged(DomainEvent):
    category_id: int


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

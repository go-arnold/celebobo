from typing import Protocol

from apps.catalog.domain.read_models import CategoryView, ProductCard
from apps.content.domain.read_models import ShippingInfo
from core.domain.actor import Actor


class Showcase(Protocol):
    def deals(self, actor: Actor, *, limit: int) -> list[ProductCard]: ...

    def newest(self, actor: Actor, *, limit: int) -> list[ProductCard]: ...

    def best_sellers(self, actor: Actor, *, limit: int) -> list[ProductCard]: ...

    def categories(self) -> list[CategoryView]: ...

    def in_category(self, actor: Actor, slug: str, *, limit: int) -> list[ProductCard]: ...


class ShippingSource(Protocol):
    def shipping(self) -> ShippingInfo: ...

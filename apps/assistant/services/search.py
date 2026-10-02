from collections.abc import Sequence
from typing import Any

from apps.assistant.domain.enums import EmbeddingTask
from apps.assistant.domain.queries import ProductQuery
from apps.assistant.selectors import VectorSelector
from apps.assistant.services.contracts import Embedder, ProductCards
from apps.catalog.domain.read_models import ProductCard
from core.domain.actor import Actor


class ProductSearch:
    def __init__(
        self, vectors: VectorSelector, embedder: Embedder, cards: ProductCards, *, limit: int
    ) -> None:
        self._vectors = vectors
        self._embedder = embedder
        self._cards = cards
        self._limit = limit

    def search(self, query: ProductQuery) -> list[int]:
        (vector,) = self._embedder.embed([query.query], task=EmbeddingTask.QUERY)
        return self._vectors.nearest(vector, query, limit=self._limit)

    def cards(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]:
        found = {card.id: card for card in self._cards.cards(actor, ids)}
        return [found[product_id] for product_id in ids if product_id in found]


def tool_result(cards: Sequence[ProductCard]) -> dict[str, Any]:
    return {
        "products": [
            {
                "id": card.id,
                "name": card.name,
                "category": card.category.name,
                "price": str(card.current_price),
                "regular_price": str(card.price),
                "on_sale": card.sale_price is not None,
                "in_stock": card.in_stock,
                "rating": str(card.rating),
                "url": f"/produits/{card.slug}",
            }
            for card in cards
        ]
    }

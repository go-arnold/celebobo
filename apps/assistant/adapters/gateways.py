from collections.abc import Sequence
from typing import Any

from apps.assistant.domain.prompts import delivery_line
from apps.catalog.domain.read_models import ProductCard
from apps.catalog.facades import CatalogFacade
from apps.catalog.selectors import ProductDocumentSelector
from apps.orders.facades import PromotionFacade
from core.container import container
from core.domain.actor import Actor


class CatalogDocuments:
    def documents(self, ids: Sequence[int]) -> list[dict[str, Any]]:
        return [dict(document) for document in ProductDocumentSelector().documents(list(ids))]

    def all_ids(self) -> list[int]:
        return [product_id for batch in ProductDocumentSelector().all_ids() for product_id in batch]

    def category_ids(self, category_id: int) -> list[int]:
        return ProductDocumentSelector().ids_in_category(category_id)


class CatalogCards:
    def cards(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]:
        return container.resolve(CatalogFacade).cards_for(actor, list(ids))


class OrdersDeliveryZones:
    def lines(self) -> list[str]:
        zones = container.resolve(PromotionFacade).shipping_zones(active_only=True)
        return [
            delivery_line(
                zone.name,
                zone.cities,
                zone.fee,
                zone.free_threshold,
                zone.delivery_estimate,
                default=zone.is_default,
            )
            for zone in sorted(zones, key=lambda zone: (zone.is_default, zone.position))
        ]

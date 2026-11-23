from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from apps.cagnotte.services.campaigns import CampaignService
from apps.catalog.selectors import catalog_ids_exist, product_categories
from apps.content.facades import SiteContentFacade
from apps.loyalty.facades import LoyaltyFacade, PointsFacade
from apps.orders.domain.pricing import CampaignLine, CampaignOffer
from apps.orders.domain.read_models import CampaignOrder
from apps.orders.selectors import campaign_order
from core.container import container


class CatalogCategories:
    def categories(self, product_ids: Iterable[int]) -> dict[int, frozenset[int]]:
        return product_categories(product_ids)

    def known(self, category_ids: Iterable[int], product_ids: Iterable[int]) -> bool:
        return catalog_ids_exist(category_ids, product_ids)


class OrdersSource:
    def campaign_order(self, order_id: int) -> CampaignOrder | None:
        return campaign_order(order_id)


class LoyaltyPoints:
    def enabled(self) -> bool:
        return container.resolve(LoyaltyFacade).programmes().points.enabled

    def credit(
        self,
        user_id: int,
        order_id: int,
        amount: Decimal,
        *,
        available_at: datetime,
        expires_at: datetime,
    ) -> None:
        container.resolve(PointsFacade).credit_campaign(
            user_id, order_id, amount, available_at=available_at, expires_at=expires_at
        )

    def reverse(self, order_id: int, amount: Decimal | None = None) -> Decimal:
        return container.resolve(PointsFacade).reverse_campaign(order_id, amount)


class ContentReturnPolicy:
    def return_days(self) -> int:
        return container.resolve(SiteContentFacade).public_settings().return_days


class CagnotteOffers:
    """The orders' CampaignOffers contract: the running operation, at quote and checkout."""

    def __init__(self, campaigns: CampaignService) -> None:
        self._campaigns = campaigns

    def offer(self, lines: Sequence[CampaignLine]) -> CampaignOffer | None:
        return self._campaigns.offer(lines)

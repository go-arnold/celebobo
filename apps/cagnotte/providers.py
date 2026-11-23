from django.utils import timezone

from apps.cagnotte.adapters.gateways import (
    CagnotteOffers,
    CatalogCategories,
    ContentReturnPolicy,
    LoyaltyPoints,
    OrdersSource,
)
from apps.cagnotte.facades import CagnotteFacade
from apps.cagnotte.repositories import CampaignRepository, RewardRepository
from apps.cagnotte.selectors import CampaignSelector, RewardSelector
from apps.cagnotte.services.campaigns import CampaignService, RewardService
from apps.orders.services.contracts import CampaignOffers
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def _campaigns() -> CampaignService:
    return CampaignService(
        CampaignRepository(), CatalogCategories(), LoyaltyPoints(), clock=timezone.now
    )


def register(container: Container) -> None:
    container.register(CampaignOffers, lambda _: CagnotteOffers(_campaigns()), replace=True)
    container.register(CagnotteFacade, _facade, lifetime=Lifetime.TRANSIENT)


def _facade(container: Container) -> CagnotteFacade:
    return CagnotteFacade(
        campaigns=_campaigns(),
        rewards=RewardService(
            RewardRepository(),
            CampaignRepository(),
            orders=OrdersSource(),
            catalog=CatalogCategories(),
            points=LoyaltyPoints(),
            returns=ContentReturnPolicy(),
            clock=timezone.now,
        ),
        campaign_repository=CampaignRepository(),
        reward_repository=RewardRepository(),
        campaign_selector=CampaignSelector(clock=timezone.now),
        reward_selector=RewardSelector(clock=timezone.now),
        publisher=container.resolve(EventPublisher),
    )

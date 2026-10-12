from apps.loyalty.facades import LoyaltyFacade
from apps.loyalty.repositories import LoyaltySettingsRepository
from apps.loyalty.services.settings import LoyaltySettingsService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(LoyaltyFacade, _loyalty_facade, lifetime=Lifetime.TRANSIENT)


def _loyalty_facade(container: Container) -> LoyaltyFacade:
    return LoyaltyFacade(
        settings=LoyaltySettingsService(LoyaltySettingsRepository()),
        publisher=container.resolve(EventPublisher),
    )

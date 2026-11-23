from django.utils import timezone

from apps.cash.services.contracts import ResellerLevels
from apps.orders.services.contracts import SuspensionGate
from apps.standing.adapters.gateways import (
    AccountsResellers,
    SalesAndRatings,
    StandingLevels,
    StandingSuspensions,
)
from apps.standing.facades import StandingFacade
from apps.standing.repositories import StandingRepository
from apps.standing.selectors import SanctionSelector
from apps.standing.services.standing import LevelService, SanctionService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def _sanctions() -> SanctionService:
    return SanctionService(StandingRepository(), AccountsResellers(), clock=timezone.now)


def register(container: Container) -> None:
    container.register(ResellerLevels, lambda _: StandingLevels(), replace=True)
    container.register(SuspensionGate, lambda _: StandingSuspensions(_sanctions()), replace=True)
    container.register(StandingFacade, _facade, lifetime=Lifetime.TRANSIENT)


def _facade(container: Container) -> StandingFacade:
    return StandingFacade(
        levels=LevelService(
            StandingRepository(), SalesAndRatings(), AccountsResellers(), clock=timezone.now
        ),
        sanctions=_sanctions(),
        repository=StandingRepository(),
        selector=SanctionSelector(clock=timezone.now),
        accounts=AccountsResellers(),
        publisher=container.resolve(EventPublisher),
    )

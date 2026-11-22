from django.utils import timezone

from apps.warranty.adapters.gateways import OrdersLineRefunds, OrdersLines
from apps.warranty.facades import ClaimFacade
from apps.warranty.repositories import ClaimRepository
from apps.warranty.selectors import ClaimSelector
from apps.warranty.services.claims import ClaimService
from apps.warranty.services.contracts import LineRefunds, OrderLines
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(OrderLines, lambda _: OrdersLines())
    container.register(LineRefunds, lambda _: OrdersLineRefunds())
    container.register(ClaimFacade, _claim_facade, lifetime=Lifetime.TRANSIENT)


def _claim_facade(container: Container) -> ClaimFacade:
    return ClaimFacade(
        claims=ClaimService(
            ClaimRepository(),
            container.resolve(OrderLines),
            container.resolve(LineRefunds),
            clock=timezone.now,
        ),
        repository=ClaimRepository(),
        selector=ClaimSelector(clock=timezone.now),
        publisher=container.resolve(EventPublisher),
    )

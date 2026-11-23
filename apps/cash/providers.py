from django.utils import timezone

from apps.cash.adapters.gateways import AccountsResellers, BeginnerLevels, CashAssignmentGate
from apps.cash.facades import CashFacade
from apps.cash.repositories import CashRepository
from apps.cash.selectors import CashSelector
from apps.cash.services.cash import CashService
from apps.cash.services.contracts import ResellerLevels
from apps.orders.services.contracts import CashGate
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(ResellerLevels, lambda _: BeginnerLevels())
    container.register(CashGate, lambda c: CashAssignmentGate(_service(c)), replace=True)
    container.register(CashFacade, _facade, lifetime=Lifetime.TRANSIENT)


def _service(container: Container) -> CashService:
    return CashService(
        CashRepository(),
        container.resolve(ResellerLevels),
        AccountsResellers(),
        clock=timezone.now,
    )


def _facade(container: Container) -> CashFacade:
    return CashFacade(
        cash=_service(container),
        selector=CashSelector(),
        resellers=AccountsResellers(),
        publisher=container.resolve(EventPublisher),
    )

from django.utils import timezone

from apps.loyalty.adapters.gateways import (
    AccountsPeople,
    ContentReturnPolicy,
    OrdersLedger,
)
from apps.loyalty.facades import CashbackFacade, LoyaltyFacade, LoyaltyRuleFacade, PointsFacade
from apps.loyalty.repositories import (
    CashbackRepository,
    LoyaltyRuleRepository,
    LoyaltySettingsRepository,
    PointTransactionRepository,
)
from apps.loyalty.services.cashback import CashbackService
from apps.loyalty.services.contracts import OrderLedger, People, ReturnPolicy
from apps.loyalty.services.points import PointService
from apps.loyalty.services.rules import LoyaltyRuleService
from apps.loyalty.services.settings import LoyaltySettingsService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(People, lambda _: AccountsPeople())
    container.register(OrderLedger, lambda _: OrdersLedger())
    container.register(ReturnPolicy, lambda _: ContentReturnPolicy())
    container.register(CashbackFacade, _cashback_facade, lifetime=Lifetime.TRANSIENT)
    container.register(
        LoyaltyFacade,
        _loyalty_facade,
        lifetime=Lifetime.TRANSIENT,
    )
    container.register(PointsFacade, lambda _: _points_facade(), lifetime=Lifetime.TRANSIENT)
    container.register(LoyaltyRuleFacade, lambda _: _loyalty_rule_facade(), lifetime=Lifetime.TRANSIENT)


def _loyalty_facade(container: Container) -> LoyaltyFacade:
    return LoyaltyFacade(
        settings=LoyaltySettingsService(LoyaltySettingsRepository()),
        publisher=container.resolve(EventPublisher),
    )


def _points_facade() -> PointsFacade:
    return PointsFacade(
        points=PointService(
            transactions=PointTransactionRepository(),
        ),
    )


def _loyalty_rule_facade() -> LoyaltyRuleFacade:
    return LoyaltyRuleFacade(
        rules=LoyaltyRuleService(
            rules=LoyaltyRuleRepository(),
            transactions=PointTransactionRepository(),
        ),
    )


def _cashback_facade(container: Container) -> CashbackFacade:
    return CashbackFacade(
        cashback=CashbackService(
            CashbackRepository(),
            LoyaltySettingsRepository(),
            container.resolve(OrderLedger),
            container.resolve(ReturnPolicy),
            clock=timezone.now,
        ),
    )

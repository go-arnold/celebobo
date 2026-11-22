from django.utils import timezone

from apps.loyalty.adapters.gateways import (
    AccountsReferrals,
    ContentReturnPolicy,
    LoyaltyWallet,
    OrdersLedger,
)
from apps.loyalty.facades import LoyaltyFacade, PointsFacade, PointsPrivacyFacade
from apps.loyalty.repositories import LoyaltySettingsRepository, PointsRepository
from apps.loyalty.services.contracts import OrderLedger, Referrals, ReturnPolicy
from apps.loyalty.services.points import PointsService
from apps.loyalty.services.settings import LoyaltySettingsService
from apps.orders.services.contracts import Wallet
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(Wallet, lambda _: LoyaltyWallet(), replace=True)
    container.register(OrderLedger, lambda _: OrdersLedger())
    container.register(ReturnPolicy, lambda _: ContentReturnPolicy())
    container.register(Referrals, lambda _: AccountsReferrals())
    container.register(PointsFacade, _points_facade, lifetime=Lifetime.TRANSIENT)
    container.register(LoyaltyFacade, _loyalty_facade, lifetime=Lifetime.TRANSIENT)
    container.register(
        PointsPrivacyFacade,
        lambda _: PointsPrivacyFacade(points=PointsRepository()),
        lifetime=Lifetime.TRANSIENT,
    )


def _loyalty_facade(container: Container) -> LoyaltyFacade:
    return LoyaltyFacade(
        settings=LoyaltySettingsService(LoyaltySettingsRepository()),
        publisher=container.resolve(EventPublisher),
    )


def _points_facade(container: Container) -> PointsFacade:
    return PointsFacade(
        points=PointsService(
            PointsRepository(),
            LoyaltySettingsRepository(),
            container.resolve(OrderLedger),
            container.resolve(ReturnPolicy),
            referrals=container.resolve(Referrals),
            clock=timezone.now,
        )
    )

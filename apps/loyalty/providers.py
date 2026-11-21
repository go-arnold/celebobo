from django.utils import timezone

from apps.loyalty.adapters.gateways import (
    AccountsPeople,
    ContentReturnPolicy,
    LoyaltyMembers,
    LoyaltyWallet,
    OrdersLedger,
)
from apps.loyalty.facades import LoyaltyFacade, MembershipFacade, PointsFacade
from apps.loyalty.repositories import (
    LoyaltySettingsRepository,
    MembershipRepository,
    MembershipRequestRepository,
    PointsRepository,
)
from apps.loyalty.selectors import MembershipSelector
from apps.loyalty.services.contracts import OrderLedger, People, ReturnPolicy
from apps.loyalty.services.membership import MembershipService
from apps.loyalty.services.points import PointsService
from apps.loyalty.services.settings import LoyaltySettingsService
from apps.orders.services.contracts import Members, Wallet
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(People, lambda _: AccountsPeople())
    container.register(Members, lambda _: LoyaltyMembers(), replace=True)
    container.register(Wallet, lambda _: LoyaltyWallet(), replace=True)
    container.register(OrderLedger, lambda _: OrdersLedger())
    container.register(ReturnPolicy, lambda _: ContentReturnPolicy())
    container.register(PointsFacade, _points_facade, lifetime=Lifetime.TRANSIENT)
    container.register(LoyaltyFacade, _loyalty_facade, lifetime=Lifetime.TRANSIENT)
    container.register(MembershipFacade, _membership_facade, lifetime=Lifetime.TRANSIENT)


def _loyalty_facade(container: Container) -> LoyaltyFacade:
    return LoyaltyFacade(
        settings=LoyaltySettingsService(LoyaltySettingsRepository()),
        publisher=container.resolve(EventPublisher),
    )


def _membership_facade(container: Container) -> MembershipFacade:
    people = container.resolve(People)
    return MembershipFacade(
        memberships=MembershipService(
            MembershipRepository(),
            MembershipRequestRepository(),
            LoyaltySettingsRepository(),
            people,
            clock=timezone.now,
        ),
        selector=MembershipSelector(),
        people=people,
        publisher=container.resolve(EventPublisher),
        clock=timezone.now,
    )


def _points_facade(container: Container) -> PointsFacade:
    return PointsFacade(
        points=PointsService(
            PointsRepository(),
            LoyaltySettingsRepository(),
            MembershipRepository(),
            container.resolve(OrderLedger),
            container.resolve(ReturnPolicy),
            clock=timezone.now,
        )
    )

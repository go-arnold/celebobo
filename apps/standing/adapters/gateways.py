from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from apps.accounts.facades import ResellerAccountFacade
from apps.accounts.selectors import SellerSelector
from apps.cash.domain.rules import Level
from apps.orders.selectors import rating_summaries
from apps.sales.selectors import validated_sales
from apps.standing.repositories import StandingRepository
from apps.standing.services.standing import SanctionService
from core.container import container
from core.domain.actor import Actor, Role


class SalesAndRatings:
    def validated_sales(
        self, reseller_ids: Iterable[int], *, since: datetime, validated_before: datetime
    ) -> dict[int, Decimal]:
        return validated_sales(reseller_ids, since=since, validated_before=validated_before)

    def ratings(self, reseller_ids: Iterable[int]) -> dict[int, Decimal | None]:
        return {
            reseller_id: summary.average
            for reseller_id, summary in rating_summaries(reseller_ids).items()
        }


class AccountsResellers:
    def active_resellers(self) -> list[tuple[int, str]]:
        selector = SellerSelector()
        return [
            (profile.id, profile.name)
            for profile in selector.resellers()
            if selector.profile(profile.id) is not None
        ]

    def is_reseller(self, user_id: int) -> bool:
        profile = SellerSelector().profile(user_id)
        return profile is not None and profile.role is Role.RESELLER

    def names(self, user_ids: Iterable[int]) -> dict[int, str]:
        return SellerSelector().names(user_ids)

    def deactivate(self, actor: Actor, reseller_id: int) -> None:
        container.resolve(ResellerAccountFacade).set_active(actor, reseller_id, active=False)


class StandingLevels:
    """The cash app's `ResellerLevels`: the cap follows the level of the last review."""

    def levels(self, reseller_ids: Iterable[int]) -> dict[int, Level]:
        return StandingRepository().levels(reseller_ids)


class StandingSuspensions:
    """The orders' `SuspensionGate`: a suspended reseller gets no new orders."""

    def __init__(self, sanctions: SanctionService) -> None:
        self._sanctions = sanctions

    def suspended_until(self, reseller_id: int) -> datetime | None:
        return self._sanctions.suspended([reseller_id]).get(reseller_id)

    def suspended(self, reseller_ids: Iterable[int]) -> dict[int, datetime]:
        return self._sanctions.suspended(reseller_ids)

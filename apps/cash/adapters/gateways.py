from collections.abc import Iterable

from apps.accounts.selectors import SellerSelector
from apps.cash.domain.rules import Level
from apps.cash.services.cash import CashService
from core.domain.actor import Role


class AccountsResellers:
    def is_reseller(self, user_id: int) -> bool:
        profile = SellerSelector().profile(user_id)
        return profile is not None and profile.role is Role.RESELLER

    def names(self, user_ids: Iterable[int]) -> dict[int, str]:
        return SellerSelector().names(user_ids)

    def all(self) -> list[tuple[int, str]]:
        return [(profile.id, profile.name) for profile in SellerSelector().resellers()]


class BeginnerLevels:
    """Every reseller is a beginner until the levels of step 7.5 exist."""

    def levels(self, reseller_ids: Iterable[int]) -> dict[int, Level]:
        return dict.fromkeys(reseller_ids, Level.BEGINNER)


class CashAssignmentGate:
    """The orders' `CashGate`: a reseller with cash overdue or at their cap gets no new orders."""

    def __init__(self, cash: CashService) -> None:
        self._cash = cash

    def blocked_reason(self, reseller_id: int) -> str | None:
        return self._cash.position(reseller_id).blocked_reason

    def blocked(self, reseller_ids: Iterable[int]) -> dict[int, str]:
        return {
            reseller_id: reason
            for reseller_id, position in self._cash.positions(reseller_ids).items()
            if (reason := position.blocked_reason) is not None
        }

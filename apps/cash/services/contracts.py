from collections.abc import Iterable
from typing import Protocol

from apps.cash.domain.rules import Level


class ResellerLevels(Protocol):
    """Each reseller's level (reseller policy, section 9; step 7.5). Until levels exist every
    reseller is a beginner."""

    def levels(self, reseller_ids: Iterable[int]) -> dict[int, Level]: ...


class Resellers(Protocol):
    def is_reseller(self, user_id: int) -> bool: ...

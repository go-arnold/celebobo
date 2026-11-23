from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from core.domain.actor import Actor


class Performance(Protocol):
    """What a reseller's level is reviewed on: validated sales (sales) and the rating (orders)."""

    def validated_sales(
        self, reseller_ids: Iterable[int], *, since: datetime, validated_before: datetime
    ) -> dict[int, Decimal]: ...

    def ratings(self, reseller_ids: Iterable[int]) -> dict[int, Decimal | None]: ...


class ResellerAccounts(Protocol):
    def active_resellers(self) -> list[tuple[int, str]]: ...

    def is_reseller(self, user_id: int) -> bool: ...

    def names(self, user_ids: Iterable[int]) -> dict[int, str]: ...

    # an exclusion ends the account
    def deactivate(self, actor: Actor, reseller_id: int) -> None: ...

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from apps.accounts.domain.commands import OnboardReseller, ResellerChanges, ResellerFilters
from apps.accounts.domain.read_models import (
    Invitee,
    OnboardedReseller,
    ResellerAccount,
    ResellerCounts,
)
from apps.orders.domain.read_models import ClientOrderTotals
from apps.sales.domain.read_models import SellerPerformance
from core.domain.actor import Actor


class ResellerAccounts(Protocol):
    def onboard(self, actor: Actor, command: OnboardReseller) -> OnboardedReseller: ...

    def update(
        self, actor: Actor, reseller_id: int, changes: ResellerChanges
    ) -> ResellerAccount: ...

    def set_active(self, actor: Actor, reseller_id: int, *, active: bool) -> ResellerAccount: ...

    def setup_link(self, user_id: int) -> str: ...


class ResellerDirectory(Protocol):
    def page(
        self, filters: ResellerFilters, *, offset: int, limit: int
    ) -> tuple[list[ResellerAccount], int]: ...

    def one(self, reseller_id: int) -> ResellerAccount: ...

    def ids(self) -> list[int]: ...

    def is_reseller(self, email: str) -> bool: ...

    def counts(self) -> ResellerCounts: ...

    def invitees(
        self, reseller_id: int, *, offset: int, limit: int
    ) -> tuple[list[Invitee], int]: ...

    def invitee_ids(self, reseller_id: int) -> list[int]: ...


class SalesLedger(Protocol):
    def performance(
        self, seller_ids: Iterable[int], *, since: datetime | None = None
    ) -> dict[int, SellerPerformance]: ...

    def top(self, seller_ids: Iterable[int], *, since: datetime) -> SellerPerformance | None: ...


class InviteeOrders(Protocol):
    def totals(self, client_ids: Iterable[int]) -> dict[int, ClientOrderTotals]: ...


class QrRenderer(Protocol):
    def svg_data_uri(self, content: str, *, scale: int) -> str: ...

from collections.abc import Iterable
from datetime import datetime

from apps.accounts.domain.commands import OnboardReseller, ResellerChanges, ResellerFilters
from apps.accounts.domain.read_models import (
    Invitee,
    OnboardedReseller,
    ResellerAccount,
    ResellerCounts,
)
from apps.accounts.facades import ResellerAccountFacade
from apps.accounts.selectors import ResellerDirectorySelector
from apps.orders.domain.read_models import ClientOrderTotals
from apps.orders.selectors import client_order_totals
from apps.sales.domain.read_models import SellerPerformance
from apps.sales.selectors import seller_performance, top_sellers
from core.container import container
from core.domain.actor import Actor


class AccountsResellers:
    def onboard(self, actor: Actor, command: OnboardReseller) -> OnboardedReseller:
        return container.resolve(ResellerAccountFacade).onboard(actor, command)

    def update(self, actor: Actor, reseller_id: int, changes: ResellerChanges) -> ResellerAccount:
        return container.resolve(ResellerAccountFacade).update(actor, reseller_id, changes)

    def set_active(self, actor: Actor, reseller_id: int, *, active: bool) -> ResellerAccount:
        return container.resolve(ResellerAccountFacade).set_active(
            actor, reseller_id, active=active
        )

    def setup_link(self, user_id: int) -> str:
        return container.resolve(ResellerAccountFacade).setup_link(user_id)


class AccountsDirectory:
    def __init__(self) -> None:
        self._selector = ResellerDirectorySelector()

    def page(
        self, filters: ResellerFilters, *, offset: int, limit: int
    ) -> tuple[list[ResellerAccount], int]:
        return self._selector.page(filters, offset=offset, limit=limit)

    def one(self, reseller_id: int) -> ResellerAccount:
        return self._selector.one(reseller_id)

    def ids(self) -> list[int]:
        return self._selector.ids()

    def is_reseller(self, email: str) -> bool:
        return self._selector.is_reseller(email)

    def counts(self) -> ResellerCounts:
        return self._selector.counts()

    def invitees(self, reseller_id: int, *, offset: int, limit: int) -> tuple[list[Invitee], int]:
        return self._selector.invitees(reseller_id, offset=offset, limit=limit)

    def invitee_ids(self, reseller_id: int) -> list[int]:
        return self._selector.invitee_ids(reseller_id)


class SalesPerformanceLedger:
    def performance(
        self, seller_ids: Iterable[int], *, since: datetime | None = None
    ) -> dict[int, SellerPerformance]:
        return seller_performance(seller_ids, since=since)

    def top(self, seller_ids: Iterable[int], *, since: datetime) -> SellerPerformance | None:
        ranked = top_sellers(seller_ids, since=since)
        return ranked[0] if ranked else None


class OrdersInviteeTotals:
    def totals(self, client_ids: Iterable[int]) -> dict[int, ClientOrderTotals]:
        return client_order_totals(client_ids)

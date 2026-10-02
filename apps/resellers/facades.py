from collections.abc import Callable
from datetime import datetime, timedelta

from django.db import transaction

from apps.accounts.domain.commands import ResellerChanges, ResellerFilters
from apps.accounts.domain.read_models import ResellerAccount
from apps.resellers.domain.commands import (
    ApplicationFilters,
    ApproveApplication,
    RejectApplication,
    SubmitApplication,
)
from apps.resellers.domain.errors import ApplicationNotFound, NoReferralCode
from apps.resellers.domain.events import (
    ApplicationApproved,
    ApplicationRejected,
    ApplicationSubmitted,
)
from apps.resellers.domain.read_models import (
    ApplicationView,
    InviteesPage,
    ReferralKit,
    ResellerOverview,
    ResellerStats,
    TopReseller,
)
from apps.resellers.models import ResellerApplication
from apps.resellers.repositories import ApplicationRepository
from apps.resellers.selectors import ApplicationSelector
from apps.resellers.services.applications import ApplicationService
from apps.resellers.services.contracts import ResellerAccounts, ResellerDirectory, SalesLedger
from apps.resellers.services.invitees import InviteeService
from apps.resellers.services.referrals import ReferralKitBuilder
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class ApplicationFacade:
    def __init__(
        self,
        *,
        applications: ApplicationService,
        repository: ApplicationRepository,
        selector: ApplicationSelector,
        publisher: EventPublisher,
    ) -> None:
        self._applications = applications
        self._repository = repository
        self._selector = selector
        self._publisher = publisher

    def submit(self, actor: Actor, command: SubmitApplication) -> ApplicationView:
        with transaction.atomic():
            application = self._applications.submit(actor, command)
            self._publisher.publish(
                ApplicationSubmitted(application_id=application.pk, actor_id=actor.user_id)
            )
        return self._selector.one(application.pk)

    def page(
        self, filters: ApplicationFilters, *, offset: int, limit: int
    ) -> tuple[list[ApplicationView], int, dict[str, int]]:
        return self._selector.page(filters, offset=offset, limit=limit)

    def detail(self, application_id: int) -> ApplicationView:
        return self._selector.one(application_id)

    def approve(
        self, actor: Actor, application_id: int, command: ApproveApplication
    ) -> ApplicationView:
        with transaction.atomic():
            application = self._locked(application_id)
            onboarded = self._applications.approve(actor, application, command)
            self._publisher.publish(
                ApplicationApproved(
                    application_id=application_id,
                    reseller_id=onboarded.user_id,
                    account_created=onboarded.created,
                    actor_id=actor.user_id,
                )
            )
        return self._selector.one(application_id)

    def reject(
        self, actor: Actor, application_id: int, command: RejectApplication
    ) -> ApplicationView:
        with transaction.atomic():
            self._applications.reject(actor, self._locked(application_id), command)
            self._publisher.publish(
                ApplicationRejected(application_id=application_id, actor_id=actor.user_id)
            )
        return self._selector.one(application_id)

    def _locked(self, application_id: int) -> ResellerApplication:
        application = self._repository.get(application_id, for_update=True)
        if application is None:
            raise ApplicationNotFound
        return application


@logged_facade
class ResellerProgramFacade:
    def __init__(
        self,
        *,
        accounts: ResellerAccounts,
        directory: ResellerDirectory,
        ledger: SalesLedger,
        invitees: InviteeService,
        applications: ApplicationSelector,
        ranking_days: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._accounts = accounts
        self._directory = directory
        self._ledger = ledger
        self._invitees = invitees
        self._applications = applications
        self._ranking_days = ranking_days
        self._clock = clock

    def page(
        self, filters: ResellerFilters, *, offset: int, limit: int
    ) -> tuple[list[ResellerOverview], int]:
        accounts, total = self._directory.page(filters, offset=offset, limit=limit)
        return self._overviews(accounts), total

    def detail(self, reseller_id: int) -> ResellerOverview:
        return self._overview(self._directory.one(reseller_id))

    def update(self, actor: Actor, reseller_id: int, changes: ResellerChanges) -> ResellerOverview:
        return self._overview(self._accounts.update(actor, reseller_id, changes))

    def set_active(self, actor: Actor, reseller_id: int, *, active: bool) -> ResellerOverview:
        return self._overview(self._accounts.set_active(actor, reseller_id, active=active))

    def invitees(self, reseller_id: int, *, offset: int, limit: int) -> tuple[InviteesPage, int]:
        return self._invitees.page(reseller_id, offset=offset, limit=limit)

    def stats(self) -> ResellerStats:
        counts = self._directory.counts()
        since = self._clock() - timedelta(days=self._ranking_days)
        best = self._ledger.top(self._directory.ids(), since=since)
        return ResellerStats(
            total=counts.total,
            active=counts.active,
            invited_clients=counts.invited_clients,
            pending_applications=self._applications.counts()["pending"],
            period_days=self._ranking_days,
            top_reseller=TopReseller(
                id=best.seller_id,
                name=self._directory.one(best.seller_id).name,
                revenue=best.revenue,
            )
            if best
            else None,
        )

    def _overview(self, account: ResellerAccount) -> ResellerOverview:
        return self._overviews([account])[0]

    def _overviews(self, accounts: list[ResellerAccount]) -> list[ResellerOverview]:
        performance = self._ledger.performance(account.id for account in accounts)
        return [
            ResellerOverview(account=account, performance=performance[account.id])
            for account in accounts
        ]


@logged_facade
class ReferralFacade:
    def __init__(
        self,
        *,
        directory: ResellerDirectory,
        invitees: InviteeService,
        kits: ReferralKitBuilder,
    ) -> None:
        self._directory = directory
        self._invitees = invitees
        self._kits = kits

    def kit(self, actor: Actor) -> ReferralKit:
        code = self._directory.one(_user_id(actor)).referral_code
        if not code:
            raise NoReferralCode
        return self._kits.build(code)

    def invitees(self, actor: Actor, *, offset: int, limit: int) -> tuple[InviteesPage, int]:
        return self._invitees.page(_user_id(actor), offset=offset, limit=limit)


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id

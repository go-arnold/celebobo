from django.conf import settings
from django.utils import timezone

from apps.resellers.adapters.gateways import (
    AccountsDirectory,
    AccountsResellers,
    OrdersInviteeTotals,
    SalesPerformanceLedger,
)
from apps.resellers.adapters.qr import SegnoQrRenderer
from apps.resellers.conf import reseller_settings
from apps.resellers.facades import ApplicationFacade, ReferralFacade, ResellerProgramFacade
from apps.resellers.repositories import ApplicationRepository
from apps.resellers.selectors import ApplicationSelector
from apps.resellers.services.applications import ApplicationService
from apps.resellers.services.contracts import (
    InviteeOrders,
    QrRenderer,
    ResellerAccounts,
    ResellerDirectory,
    SalesLedger,
)
from apps.resellers.services.invitees import InviteeService
from apps.resellers.services.mailer import ApplicationMailer
from apps.resellers.services.referrals import ReferralKitBuilder
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher

LOGIN_PATH = "/connexion"


def register(container: Container) -> None:
    container.register(ResellerAccounts, lambda _: AccountsResellers())
    container.register(ResellerDirectory, lambda _: AccountsDirectory())
    container.register(SalesLedger, lambda _: SalesPerformanceLedger())
    container.register(InviteeOrders, lambda _: OrdersInviteeTotals())
    container.register(QrRenderer, lambda _: SegnoQrRenderer())
    container.register(ApplicationMailer, _mailer, lifetime=Lifetime.TRANSIENT)
    container.register(ApplicationFacade, _application_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ResellerProgramFacade, _program_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ReferralFacade, _referral_facade, lifetime=Lifetime.TRANSIENT)


def _invitees(container: Container) -> InviteeService:
    return InviteeService(container.resolve(ResellerDirectory), container.resolve(InviteeOrders))


def _mailer(container: Container) -> ApplicationMailer:
    return ApplicationMailer(
        container.resolve(ResellerAccounts),
        base_url=str(settings.FRONTEND_URL),
        login_path=LOGIN_PATH,
    )


def _application_facade(container: Container) -> ApplicationFacade:
    repository = ApplicationRepository()
    return ApplicationFacade(
        applications=ApplicationService(
            repository,
            container.resolve(ResellerAccounts),
            container.resolve(ResellerDirectory),
            clock=timezone.now,
        ),
        repository=repository,
        selector=ApplicationSelector(),
        publisher=container.resolve(EventPublisher),
    )


def _program_facade(container: Container) -> ResellerProgramFacade:
    return ResellerProgramFacade(
        accounts=container.resolve(ResellerAccounts),
        directory=container.resolve(ResellerDirectory),
        ledger=container.resolve(SalesLedger),
        invitees=_invitees(container),
        applications=ApplicationSelector(),
        ranking_days=reseller_settings().ranking_days,
        clock=timezone.now,
    )


def _referral_facade(container: Container) -> ReferralFacade:
    return ReferralFacade(
        directory=container.resolve(ResellerDirectory),
        invitees=_invitees(container),
        kits=ReferralKitBuilder(
            container.resolve(QrRenderer),
            reseller_settings(),
            base_url=str(settings.FRONTEND_URL),
        ),
    )

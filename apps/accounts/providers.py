from allauth.account import app_settings as account_settings

from apps.accounts.adapters.allauth import AllauthEmailVerifier, AllauthPasswordSetupLinks
from apps.accounts.adapters.security import (
    CacheTicketStore,
    DjangoGroupSync,
    DjangoPasswordPolicy,
    SimpleJwtTokenRevoker,
)
from apps.accounts.facades import (
    AccountFacade,
    AddressBookFacade,
    PreferencesFacade,
    RealtimeAccessFacade,
    ResellerAccountFacade,
    UserAdminFacade,
)
from apps.accounts.repositories import AddressRepository, PreferenceRepository, UserRepository
from apps.accounts.selectors import (
    AddressSelector,
    ProfileSelector,
    ResellerDirectorySelector,
    UserDirectorySelector,
)
from apps.accounts.services.access import AccessService
from apps.accounts.services.addresses import AddressBookService
from apps.accounts.services.contracts import (
    EmailVerifier,
    GroupSync,
    PasswordPolicy,
    PasswordSetupLinks,
    TicketStore,
    TokenRevoker,
)
from apps.accounts.services.mailer import AccountMailer
from apps.accounts.services.preferences import PreferenceService
from apps.accounts.services.profiles import ProfileService
from apps.accounts.services.referrals import ReferralService
from apps.accounts.services.registration import RegistrationService
from apps.accounts.services.resellers import ResellerAccountService
from apps.accounts.services.roles import RoleService
from apps.accounts.services.tickets import TicketService
from apps.accounts.services.user_admin import UserAdminService
from core.authz.catalog import permission_catalog
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(PasswordPolicy, lambda _: DjangoPasswordPolicy())
    container.register(TokenRevoker, lambda _: SimpleJwtTokenRevoker())
    container.register(EmailVerifier, lambda _: AllauthEmailVerifier())
    container.register(GroupSync, lambda _: DjangoGroupSync())
    container.register(TicketStore, lambda _: CacheTicketStore())
    container.register(PasswordSetupLinks, lambda _: AllauthPasswordSetupLinks())

    container.register(AccountFacade, _account_facade, lifetime=Lifetime.TRANSIENT)
    container.register(AddressBookFacade, _address_book_facade, lifetime=Lifetime.TRANSIENT)
    container.register(PreferencesFacade, _preferences_facade, lifetime=Lifetime.TRANSIENT)
    container.register(RealtimeAccessFacade, _realtime_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ResellerAccountFacade, _reseller_facade, lifetime=Lifetime.TRANSIENT)
    container.register(UserAdminFacade, _user_admin_facade, lifetime=Lifetime.TRANSIENT)
    container.register(
        AccountMailer,
        lambda c: AccountMailer(UserRepository(), c.resolve(PasswordSetupLinks)),
        lifetime=Lifetime.TRANSIENT,
    )


def _account_facade(container: Container) -> AccountFacade:
    users = UserRepository()
    referrals = ReferralService(users)
    return AccountFacade(
        registration=RegistrationService(users, referrals, container.resolve(PasswordPolicy)),
        profiles=ProfileService(users, AddressRepository(), referrals),
        roles=RoleService(users, referrals, container.resolve(GroupSync)),
        selector=ProfileSelector(permission_catalog),
        verifier=container.resolve(EmailVerifier),
        revoker=container.resolve(TokenRevoker),
        publisher=container.resolve(EventPublisher),
        verification_required=(
            account_settings.EMAIL_VERIFICATION
            == account_settings.EmailVerificationMethod.MANDATORY
        ),
    )


def _address_book_facade(_: Container) -> AddressBookFacade:
    return AddressBookFacade(
        book=AddressBookService(AddressRepository()), selector=AddressSelector()
    )


def _preferences_facade(_: Container) -> PreferencesFacade:
    return PreferencesFacade(preferences=PreferenceService(PreferenceRepository()))


def _realtime_facade(container: Container) -> RealtimeAccessFacade:
    return RealtimeAccessFacade(tickets=TicketService(container.resolve(TicketStore)))


def _reseller_facade(container: Container) -> ResellerAccountFacade:
    users = UserRepository()
    return ResellerAccountFacade(
        accounts=ResellerAccountService(
            users,
            ReferralService(users),
            container.resolve(GroupSync),
            AccessService(users, container.resolve(TokenRevoker)),
        ),
        selector=ResellerDirectorySelector(),
        verifier=container.resolve(EmailVerifier),
        links=container.resolve(PasswordSetupLinks),
        users=users,
        publisher=container.resolve(EventPublisher),
    )


def _user_admin_facade(container: Container) -> UserAdminFacade:
    users = UserRepository()
    return UserAdminFacade(
        admin=UserAdminService(
            users,
            RoleService(users, ReferralService(users), container.resolve(GroupSync)),
            AccessService(users, container.resolve(TokenRevoker)),
        ),
        selector=UserDirectorySelector(),
        verifier=container.resolve(EmailVerifier),
        publisher=container.resolve(EventPublisher),
    )

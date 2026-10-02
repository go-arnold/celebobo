from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.accounts.domain.commands import (
    AddressChanges,
    AddressFields,
    ChangeRole,
    CreateUser,
    EditUser,
    OnboardReseller,
    RegisterUser,
    ResellerChanges,
    SetAvailability,
    UpdatePreferences,
    UpdateProfile,
    UserFilters,
)
from apps.accounts.domain.errors import InactiveAccount, UserNotFound
from apps.accounts.domain.events import (
    AccountDeleted,
    AvailabilityChanged,
    PasswordResetRequested,
    ProfileUpdated,
    ReferralAttached,
    ResellerOnboarded,
    ResellerUpdated,
    RoleChanged,
    UserActivationChanged,
    UserCreated,
    UserEdited,
    UserRegistered,
)
from apps.accounts.domain.read_models import (
    AddressView,
    OnboardedReseller,
    Profile,
    ResellerAccount,
    UserRow,
    WsTicket,
)
from apps.accounts.selectors import (
    AddressSelector,
    ProfileSelector,
    ResellerDirectorySelector,
    UserDirectorySelector,
    to_address_view,
)
from apps.accounts.services.addresses import AddressBookService
from apps.accounts.services.contracts import (
    EmailVerifier,
    PasswordSetupLinks,
    TokenRevoker,
    UserStore,
)
from apps.accounts.services.preferences import Preferences, PreferenceService
from apps.accounts.services.profiles import ProfileService
from apps.accounts.services.registration import RegistrationService
from apps.accounts.services.resellers import ResellerAccountService
from apps.accounts.services.roles import RoleService
from apps.accounts.services.tickets import TicketService
from apps.accounts.services.user_admin import UserAdminService
from core.domain.actor import Actor, Role
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@dataclass(frozen=True, slots=True)
class Registration:
    user_id: int
    email: str
    verification_required: bool


@logged_facade
class AccountFacade:
    def __init__(
        self,
        *,
        registration: RegistrationService,
        profiles: ProfileService,
        roles: RoleService,
        selector: ProfileSelector,
        verifier: EmailVerifier,
        revoker: TokenRevoker,
        publisher: EventPublisher,
        verification_required: bool,
    ) -> None:
        self._registration = registration
        self._profiles = profiles
        self._roles = roles
        self._selector = selector
        self._verifier = verifier
        self._revoker = revoker
        self._publisher = publisher
        self._verification_required = verification_required

    def register(self, command: RegisterUser) -> Registration:
        with transaction.atomic():
            user = self._registration.register(command)
            self._verifier.register_address(user)
            self._publisher.publish(
                UserRegistered(user_id=user.pk, invited_by_id=user.invited_by_id)
            )
        return Registration(user.pk, user.email, self._verification_required)

    def complete_social_signup(self, user_id: int) -> None:
        self._publisher.publish(UserRegistered(user_id=user_id, via_social=True))

    def update_profile(self, actor: Actor, command: UpdateProfile) -> Profile:
        user_id = _user_id(actor)
        with transaction.atomic():
            change = self._profiles.update(user_id, command)
            if change.fields:
                self._publisher.publish(
                    ProfileUpdated(user_id=user_id, fields=change.fields, actor_id=user_id)
                )
            if change.attached_reseller_id is not None:
                self._publisher.publish(
                    ReferralAttached(
                        user_id=user_id,
                        reseller_id=change.attached_reseller_id,
                        actor_id=user_id,
                    )
                )
        return self._selector.profile(user_id)

    def delete_account(self, actor: Actor) -> None:
        user_id = _user_id(actor)
        with transaction.atomic():
            self._profiles.anonymize(user_id, now=timezone.now())
            self._revoker.revoke_all(user_id)
            self._publisher.publish(AccountDeleted(user_id=user_id, actor_id=user_id))

    def change_role(self, actor: Actor, command: ChangeRole) -> Profile:
        with transaction.atomic():
            change = self._roles.change(actor, command)
            if change.changed:
                self._publisher.publish(
                    RoleChanged(
                        user_id=command.user_id,
                        previous_role=change.previous_role,
                        role=command.role,
                        actor_id=actor.user_id,
                    )
                )
        return self._selector.profile(command.user_id)

    def set_availability(self, actor: Actor, command: SetAvailability) -> Profile:
        user_id = _user_id(actor)
        with transaction.atomic():
            self._roles.set_availability(user_id, command)
            self._publisher.publish(
                AvailabilityChanged(
                    user_id=user_id, availability=command.availability, actor_id=user_id
                )
            )
        return self._selector.profile(user_id)


@logged_facade
class ResellerAccountFacade:
    def __init__(
        self,
        *,
        accounts: ResellerAccountService,
        selector: ResellerDirectorySelector,
        verifier: EmailVerifier,
        links: PasswordSetupLinks,
        users: UserStore,
        publisher: EventPublisher,
    ) -> None:
        self._accounts = accounts
        self._selector = selector
        self._verifier = verifier
        self._links = links
        self._users = users
        self._publisher = publisher

    def onboard(self, actor: Actor, command: OnboardReseller) -> OnboardedReseller:
        with transaction.atomic():
            onboarding = self._accounts.onboard(command)
            user = onboarding.user
            if onboarding.created:
                self._verifier.register_address(user, verified=True)
            self._publisher.publish(
                ResellerOnboarded(
                    user_id=user.pk, created=onboarding.created, actor_id=actor.user_id
                )
            )
            if onboarding.previous_role is not Role.RESELLER:
                self._publisher.publish(
                    RoleChanged(
                        user_id=user.pk,
                        previous_role=onboarding.previous_role,
                        role=Role.RESELLER,
                        actor_id=actor.user_id,
                    )
                )
        return OnboardedReseller(user_id=user.pk, created=onboarding.created)

    def update(self, actor: Actor, reseller_id: int, changes: ResellerChanges) -> ResellerAccount:
        with transaction.atomic():
            fields = self._accounts.update(reseller_id, changes)
            if fields:
                self._publisher.publish(
                    ResellerUpdated(user_id=reseller_id, fields=fields, actor_id=actor.user_id)
                )
        return self._selector.one(reseller_id)

    def set_active(self, actor: Actor, reseller_id: int, *, active: bool) -> ResellerAccount:
        with transaction.atomic():
            if self._accounts.set_active(reseller_id, active=active):
                self._publisher.publish(
                    UserActivationChanged(
                        user_id=reseller_id, active=active, actor_id=actor.user_id
                    )
                )
        return self._selector.one(reseller_id)

    def setup_link(self, user_id: int) -> str:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFound
        return self._links.link_for(user)


@logged_facade
class UserAdminFacade:
    def __init__(
        self,
        *,
        admin: UserAdminService,
        selector: UserDirectorySelector,
        verifier: EmailVerifier,
        publisher: EventPublisher,
    ) -> None:
        self._admin = admin
        self._selector = selector
        self._verifier = verifier
        self._publisher = publisher

    def page(
        self, filters: UserFilters, *, offset: int, limit: int
    ) -> tuple[list[UserRow], int, dict[str, int]]:
        return self._selector.page(filters, offset=offset, limit=limit)

    def detail(self, user_id: int) -> UserRow:
        return self._selector.one(user_id)

    def create(self, actor: Actor, command: CreateUser) -> UserRow:
        with transaction.atomic():
            user = self._admin.create(command)
            self._verifier.register_address(user, verified=True)
            self._publisher.publish(
                UserCreated(user_id=user.pk, role=command.role, actor_id=actor.user_id)
            )
        return self._selector.one(user.pk)

    def edit(self, actor: Actor, user_id: int, command: EditUser) -> UserRow:
        with transaction.atomic():
            user, fields = self._admin.edit(user_id, command)
            if "email" in fields:
                self._verifier.register_address(user, verified=True)
            if fields:
                self._publisher.publish(
                    UserEdited(user_id=user_id, fields=fields, actor_id=actor.user_id)
                )
        return self._selector.one(user_id)

    def set_active(self, actor: Actor, user_id: int, *, active: bool) -> UserRow:
        with transaction.atomic():
            if self._admin.set_active(actor, user_id, active=active):
                self._publisher.publish(
                    UserActivationChanged(user_id=user_id, active=active, actor_id=actor.user_id)
                )
        return self._selector.one(user_id)

    def send_password_reset(self, actor: Actor, user_id: int) -> None:
        if not self._admin.get(user_id).is_active:
            raise InactiveAccount
        self._publisher.publish(PasswordResetRequested(user_id=user_id, actor_id=actor.user_id))


@logged_facade
class AddressBookFacade:
    def __init__(self, *, book: AddressBookService, selector: AddressSelector) -> None:
        self._book = book
        self._selector = selector

    def add(self, actor: Actor, fields: AddressFields) -> AddressView:
        with transaction.atomic():
            return to_address_view(self._book.add(_user_id(actor), fields))

    def update(self, actor: Actor, address_id: int, changes: AddressChanges) -> AddressView:
        with transaction.atomic():
            return to_address_view(self._book.update(_user_id(actor), address_id, changes))

    def remove(self, actor: Actor, address_id: int) -> None:
        with transaction.atomic():
            self._book.remove(_user_id(actor), address_id)

    def set_default(self, actor: Actor, address_id: int) -> AddressView:
        with transaction.atomic():
            return to_address_view(self._book.set_default(_user_id(actor), address_id))


@logged_facade
class PreferencesFacade:
    def __init__(self, *, preferences: PreferenceService) -> None:
        self._preferences = preferences

    def current(self, actor: Actor) -> Preferences:
        return self._preferences.current(_user_id(actor))

    def update(self, actor: Actor, command: UpdatePreferences) -> Preferences:
        with transaction.atomic():
            return self._preferences.update(_user_id(actor), command)


@logged_facade
class RealtimeAccessFacade:
    def __init__(self, *, tickets: TicketService) -> None:
        self._tickets = tickets

    def issue_ticket(self, actor: Actor) -> WsTicket:
        return self._tickets.issue(_user_id(actor))

    def redeem_ticket(self, ticket: str) -> int | None:
        return self._tickets.redeem(ticket)


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id

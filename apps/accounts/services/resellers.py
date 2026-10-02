from dataclasses import dataclass

from apps.accounts.domain.commands import OnboardReseller, ResellerChanges
from apps.accounts.domain.enums import STAFF_ROLES, Availability
from apps.accounts.domain.errors import (
    AlreadyReseller,
    InvalidManager,
    PhoneAlreadyUsed,
    ResellerNotFound,
    StaffCannotBecomeReseller,
)
from apps.accounts.domain.normalization import clean_text, normalize_email, normalize_phone
from apps.accounts.models import DEFAULT_COMMISSION_RATE, User
from apps.accounts.services.contracts import GroupSync, TokenRevoker, UserStore
from apps.accounts.services.referrals import ReferralService
from core.domain.actor import Role
from core.domain.values import provided


@dataclass(frozen=True, slots=True)
class Onboarding:
    user: User
    created: bool
    previous_role: Role


class ResellerAccountService:
    def __init__(
        self,
        users: UserStore,
        referrals: ReferralService,
        groups: GroupSync,
        revoker: TokenRevoker,
    ) -> None:
        self._users = users
        self._referrals = referrals
        self._groups = groups
        self._revoker = revoker

    def onboard(self, command: OnboardReseller) -> Onboarding:
        manager_id = self._manager(command.manager_id)
        email = normalize_email(command.email)
        user = self._users.by_email(email, for_update=True)
        created = user is None
        if user is None:
            user = self._create(email, command)
        elif user.account_role in STAFF_ROLES:
            raise StaffCannotBecomeReseller
        elif user.account_role is Role.RESELLER and user.is_active:
            raise AlreadyReseller
        previous = Role.CLIENT if created else user.account_role
        user.role = Role.RESELLER.value
        user.is_staff = False
        user.is_active = True
        user.availability = Availability.OFFLINE.value
        user.commission_rate = command.commission_rate or DEFAULT_COMMISSION_RATE
        user.manager_id = manager_id
        fields = ["role", "is_staff", "is_active", "availability", "commission_rate", "manager"]
        if not user.referral_code:
            user.referral_code = self._referrals.issue_code()
            fields.append("referral_code")
        self._users.save(user, fields=fields)
        self._groups.sync(user, Role.RESELLER)
        return Onboarding(user, created, previous)

    def update(self, reseller_id: int, changes: ResellerChanges) -> tuple[str, ...]:
        user = self._reseller(reseller_id)
        values = dict(provided(changes))
        if "manager_id" in values:
            values["manager_id"] = self._manager(values["manager_id"])
        changed = tuple(name for name, value in values.items() if getattr(user, name) != value)
        for name in changed:
            setattr(user, name, values[name])
        if changed:
            self._users.save(user, fields=[name.removesuffix("_id") for name in changed])
        return changed

    def set_active(self, reseller_id: int, *, active: bool) -> bool:
        user = self._reseller(reseller_id)
        if user.is_active is active:
            return False
        user.is_active = active
        user.availability = Availability.OFFLINE.value
        self._users.save(user, fields=("is_active", "availability"))
        if not active:
            self._revoker.revoke_all(user.pk)
        return True

    def _create(self, email: str, command: OnboardReseller) -> User:
        phone = normalize_phone(command.phone_number)
        if phone and self._users.phone_taken(phone):
            raise PhoneAlreadyUsed
        return self._users.create_invited(
            email=email,
            first_name=clean_text(command.first_name),
            last_name=clean_text(command.last_name),
            phone_number=phone,
        )

    def _reseller(self, reseller_id: int) -> User:
        user = self._users.get(reseller_id, for_update=True)
        if user is None or user.account_role is not Role.RESELLER:
            raise ResellerNotFound
        return user

    def _manager(self, manager_id: int | None) -> int | None:
        if manager_id is None:
            return None
        if self._users.active_staff(manager_id) is None:
            raise InvalidManager
        return manager_id

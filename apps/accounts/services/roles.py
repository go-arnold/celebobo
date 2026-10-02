from dataclasses import dataclass

from apps.accounts.domain.commands import ChangeRole, SetAvailability
from apps.accounts.domain.enums import ACCOUNT_ROLES, STAFF_ROLES, Availability
from apps.accounts.domain.errors import InvalidRole, NotAReseller, OwnRoleChange, UserNotFound
from apps.accounts.models import DEFAULT_COMMISSION_RATE, User
from apps.accounts.services.contracts import GroupSync, UserStore
from apps.accounts.services.referrals import ReferralService
from core.domain.actor import Actor, Role


@dataclass(frozen=True, slots=True)
class RoleChange:
    user: User
    previous_role: Role
    changed: bool


class RoleService:
    def __init__(self, users: UserStore, referrals: ReferralService, groups: GroupSync) -> None:
        self._users = users
        self._referrals = referrals
        self._groups = groups

    def change(self, actor: Actor, command: ChangeRole) -> RoleChange:
        if actor.owns(command.user_id):
            raise OwnRoleChange
        if command.role not in ACCOUNT_ROLES:
            raise InvalidRole
        user = self._users.get(command.user_id, for_update=True)
        if user is None:
            raise UserNotFound
        previous = user.account_role
        if previous is command.role:
            return RoleChange(user, previous, changed=False)

        user.role = command.role.value
        user.is_staff = command.role in STAFF_ROLES
        fields = ["role", "is_staff"]
        if command.role is Role.RESELLER:
            fields += self._prepare_reseller(user)
        self._users.save(user, fields=fields)
        self._groups.sync(user, command.role)
        return RoleChange(user, previous, changed=True)

    def set_availability(self, user_id: int, command: SetAvailability) -> User:
        user = self._users.get(user_id, for_update=True)
        if user is None:
            raise UserNotFound
        if user.account_role is not Role.RESELLER:
            raise NotAReseller
        user.availability = command.availability.value
        self._users.save(user, fields=("availability",))
        return user

    def _prepare_reseller(self, user: User) -> list[str]:
        user.availability = Availability.OFFLINE.value
        user.commission_rate = DEFAULT_COMMISSION_RATE
        fields = ["availability", "commission_rate"]
        if not user.referral_code:
            user.referral_code = self._referrals.issue_code()
            fields.append("referral_code")
        return fields

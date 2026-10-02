from apps.accounts.domain.commands import CreateUser, EditUser
from apps.accounts.domain.enums import ACCOUNT_ROLES
from apps.accounts.domain.errors import (
    EmailAlreadyUsed,
    InvalidRole,
    OwnAccountDeactivation,
    PhoneAlreadyUsed,
    UserNotFound,
)
from apps.accounts.domain.normalization import clean_text, normalize_email, normalize_phone
from apps.accounts.models import User
from apps.accounts.services.access import AccessService
from apps.accounts.services.contracts import UserStore
from apps.accounts.services.roles import RoleService
from core.domain.actor import Actor
from core.domain.values import provided


class UserAdminService:
    def __init__(self, users: UserStore, roles: RoleService, access: AccessService) -> None:
        self._users = users
        self._roles = roles
        self._access = access

    def create(self, command: CreateUser) -> User:
        if command.role not in ACCOUNT_ROLES:
            raise InvalidRole
        email = self._available_email(command.email)
        user = self._users.create_invited(
            email=email,
            first_name=clean_text(command.first_name),
            last_name=clean_text(command.last_name),
            phone_number=self._available_phone(command.phone_number),
        )
        self._roles.apply(user, command.role)
        return user

    def edit(self, user_id: int, command: EditUser) -> tuple[User, tuple[str, ...]]:
        user = self.get(user_id, for_update=True)
        values = dict(provided(command))
        for name in ("first_name", "last_name"):
            if name in values:
                values[name] = clean_text(values[name])
        if "email" in values:
            values["email"] = self._available_email(values["email"], exclude_id=user.pk)
        if "phone_number" in values:
            values["phone_number"] = self._available_phone(
                values["phone_number"], exclude_id=user.pk
            )
        changed = tuple(name for name, value in values.items() if getattr(user, name) != value)
        for name in changed:
            setattr(user, name, values[name])
        if changed:
            self._users.save(user, fields=changed)
        return user, changed

    def set_active(self, actor: Actor, user_id: int, *, active: bool) -> bool:
        if actor.owns(user_id):
            raise OwnAccountDeactivation
        return self._access.set_active(self.get(user_id, for_update=True), active=active)

    def get(self, user_id: int, *, for_update: bool = False) -> User:
        user = self._users.get(user_id, for_update=for_update)
        if user is None or user.deleted_at is not None:
            raise UserNotFound
        return user

    def _available_email(self, email: str, *, exclude_id: int | None = None) -> str:
        normalized = normalize_email(email)
        if self._users.email_taken(normalized, exclude_id=exclude_id):
            raise EmailAlreadyUsed
        return normalized

    def _available_phone(self, phone: str | None, *, exclude_id: int | None = None) -> str | None:
        normalized = normalize_phone(phone)
        if normalized and self._users.phone_taken(normalized, exclude_id=exclude_id):
            raise PhoneAlreadyUsed
        return normalized

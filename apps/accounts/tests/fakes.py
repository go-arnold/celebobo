from collections.abc import Iterable
from typing import Any

from apps.accounts.models import User
from core.domain.actor import Role


class InMemoryUsers:
    def __init__(self, users: Iterable[User] = ()) -> None:
        self.users = {user.pk: user for user in users}
        self.saved: list[tuple[int, tuple[str, ...]]] = []

    def get(self, user_id: int, *, for_update: bool = False) -> User | None:
        return self.users.get(user_id)

    def create(self, *, email: str, password: str, **fields: Any) -> User:
        user = User(pk=len(self.users) + 1, email=email, **fields)
        user.set_password(password)
        self.users[user.pk] = user
        return user

    def save(self, user: User, *, fields: Iterable[str]) -> None:
        self.saved.append((user.pk, tuple(fields)))

    def email_taken(self, email: str, *, exclude_id: int | None = None) -> bool:
        return any(
            user.email.lower() == email.lower() and user.pk != exclude_id
            for user in self.users.values()
        )

    def phone_taken(self, phone_number: str, *, exclude_id: int | None = None) -> bool:
        return any(
            user.phone_number == phone_number and user.pk != exclude_id
            for user in self.users.values()
        )

    def active_reseller_by_code(self, code: str) -> User | None:
        return next(
            (
                user
                for user in self.users.values()
                if user.referral_code == code
                and user.role == Role.RESELLER.value
                and user.is_active
            ),
            None,
        )

    def referral_code_taken(self, code: str) -> bool:
        return any(user.referral_code == code for user in self.users.values())


class InMemoryPreferences:
    def __init__(self) -> None:
        self.stored: dict[int, dict[str, Any]] = {}

    def stored_for(self, user_id: int) -> dict[str, Any]:
        return self.stored.get(user_id, {})

    def store(self, user_id: int, preferences: dict[str, Any]) -> None:
        self.stored[user_id] = preferences


class InMemoryTickets:
    def __init__(self) -> None:
        self.tickets: dict[str, int] = {}

    def put(self, ticket: str, user_id: int, *, ttl: int) -> None:
        self.tickets[ticket] = user_id

    def take(self, ticket: str) -> int | None:
        return self.tickets.pop(ticket, None)


class AcceptAllPasswords:
    def validate(self, password: str, *, user: User | None = None) -> None:
        return None

from collections.abc import Callable, Iterable
from datetime import datetime

from apps.accounts.domain.consents import (
    ConsentKind,
    ConsentSource,
    PolicyVersions,
    unaccepted_required,
)
from apps.accounts.domain.errors import ConsentRequired
from apps.accounts.services.contracts import ConsentStore, UserStore


class ConsentService:
    def __init__(
        self,
        consents: ConsentStore,
        users: UserStore,
        versions: PolicyVersions,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._consents = consents
        self._users = users
        self._versions = versions
        self._clock = clock

    @staticmethod
    def require(kinds: Iterable[ConsentKind]) -> None:
        if missing := unaccepted_required(kinds):
            raise ConsentRequired(kind.value for kind in missing)

    def give(
        self, user_id: int, kinds: Iterable[ConsentKind], *, source: ConsentSource
    ) -> tuple[ConsentKind, ...]:
        """Record each consent not already given on the current version; return those recorded."""
        current = self._versions.current()
        accepted = self._consents.accepted(user_id)
        now = self._clock()
        recorded: list[ConsentKind] = []
        for kind in dict.fromkeys(kinds):
            version = current.get(kind, "")
            if accepted.get(kind) == version:
                continue
            self._consents.create(
                user_id, kind=kind, version=version, source=source, accepted_at=now
            )
            recorded.append(kind)
        return tuple(recorded)

    def give_from_account(
        self, user_id: int, kinds: Iterable[ConsentKind]
    ) -> tuple[tuple[ConsentKind, ...], ConsentSource]:
        # the first consents of an account opened with Google are given in the completion step
        # that follows the Google sign-up
        first_google = not self._consents.any_for(user_id) and self._users.signed_up_with_google(
            user_id
        )
        source = ConsentSource.GOOGLE if first_google else ConsentSource.ACCOUNT
        return self.give(user_id, kinds, source=source), source

    def withdraw(self, user_id: int, kinds: Iterable[ConsentKind]) -> tuple[ConsentKind, ...]:
        return self._consents.withdraw(user_id, kinds=kinds, at=self._clock())

    def withdraw_all(self, user_id: int) -> tuple[ConsentKind, ...]:
        return self.withdraw(user_id, ConsentKind)

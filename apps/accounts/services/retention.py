from collections.abc import Sequence
from datetime import datetime

from apps.accounts.repositories import InactiveClientRepository
from apps.accounts.services.contracts import ActivitySource, AddressStore, PersonalDataEraser
from apps.accounts.services.profiles import scrub_identity
from apps.audit.domain.retention import Expired


class InactiveAccountService:
    def __init__(
        self,
        accounts: InactiveClientRepository,
        addresses: AddressStore,
        activity: Sequence[ActivitySource],
        erasers: Sequence[PersonalDataEraser],
    ) -> None:
        self._accounts = accounts
        self._addresses = addresses
        self._activity = activity
        self._erasers = erasers

    # client accounts without sign-up or login since the cutoff, by ascending id
    def candidates(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        return self._accounts.quiet_since(cutoff, after_id=after_id, limit=limit)

    # among them, those with an order, a message, a points movement or a session since the cutoff
    def recently_active(self, batch: Sequence[Expired], cutoff: datetime) -> set[int]:
        user_ids = [row.id for row in batch]
        active: set[int] = set()
        for source in self._activity:
            active |= {
                user_id for user_id, at in source.last_activity(user_ids).items() if at >= cutoff
            }
        return active

    # the account stays (orders point to it) but nothing identifies the client any more and it
    # can no longer be used; checked again under lock in case the client came back meanwhile
    def anonymize(self, user_id: int, *, cutoff: datetime, now: datetime) -> bool:
        user = self._accounts.lock_quiet(user_id, cutoff)
        if user is None:
            return False
        self._accounts.save(user, fields=scrub_identity(user, now))
        self._addresses.delete_all_for(user_id)
        self._accounts.forget_preferences(user_id)
        for eraser in self._erasers:
            eraser.erase(user_id)
        return True

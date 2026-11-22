from collections.abc import Sequence
from datetime import datetime

from apps.accounts.domain.retention import Outcome
from apps.accounts.repositories import InactiveClientRepository
from apps.accounts.services.contracts import (
    ActivitySource,
    AddressStore,
    NewsletterSubscriptions,
    PersonalDataEraser,
)
from apps.accounts.services.profiles import scrub_identity
from apps.audit.domain.retention import Expired


class InactiveAccountService:
    def __init__(
        self,
        accounts: InactiveClientRepository,
        addresses: AddressStore,
        newsletter: NewsletterSubscriptions,
        activity: Sequence[ActivitySource],
        erasers: Sequence[PersonalDataEraser],
    ) -> None:
        self._accounts = accounts
        self._addresses = addresses
        self._newsletter = newsletter
        self._activity = activity
        self._erasers = erasers

    # client accounts without sign-up or login since the cutoff, or deleted before it and not
    # erased yet, by ascending id
    def candidates(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        return self._accounts.due(cutoff, after_id=after_id, limit=limit)

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
    # can no longer be used; checked again under lock in case the client came back meanwhile.
    # An account the client deleted already lost its identity: only the erasers run.
    def anonymize(self, user_id: int, *, cutoff: datetime, now: datetime) -> Outcome:
        user = self._accounts.lock_due(user_id, cutoff)
        if user is None:
            return Outcome.SKIPPED
        outcome = Outcome.ERASED if user.deleted_at is not None else Outcome.ANONYMIZED
        fields: tuple[str, ...] = ()
        if outcome is Outcome.ANONYMIZED:
            # read before the scrub replaces it
            self._newsletter.forget(user.email)
            fields = scrub_identity(user, now)
        user.personal_data_erased_at = now
        self._accounts.save(user, fields=(*fields, "personal_data_erased_at"))
        self._addresses.delete_all_for(user_id)
        self._accounts.forget_preferences(user_id)
        for eraser in self._erasers:
            eraser.erase(user_id)
        return outcome

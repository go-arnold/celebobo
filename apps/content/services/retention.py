from datetime import datetime

from apps.audit.domain.retention import BATCH_SIZE, RetentionReport, years_before
from apps.audit.services.retention import purge_expired
from apps.content.domain.retention import SUBSCRIBER_INACTIVITY_YEARS
from apps.content.repositories import SubscriberRepository

RULE = "content.stale_subscribers"


# seam for the marketing consents: once they record interactions (withdrawal, renewal, opens),
# `stale_before` is where a subscriber with a recent interaction gets kept
class StaleSubscriberRetention:
    label = "Abonnés à la lettre d'information sans interaction depuis 3 ans, supprimés"

    def __init__(self, subscribers: SubscriberRepository) -> None:
        self._subscribers = subscribers

    def apply(self, *, now: datetime, dry_run: bool) -> RetentionReport:
        cutoff = years_before(now, SUBSCRIBER_INACTIVITY_YEARS)
        return purge_expired(
            rule=RULE,
            label=self.label,
            fetch=lambda after: self._subscribers.stale_before(
                cutoff, after_id=after, limit=BATCH_SIZE
            ),
            delete=lambda ids: self._subscribers.delete_stale(ids, before=cutoff),
            dry_run=dry_run,
        )

from collections.abc import Callable, Collection, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from django.db import transaction

from apps.audit.domain.retention import Expired, RetentionReport, SampleCollector, in_batches
from apps.audit.repositories import ChangeRepository, EventRepository
from core.registry import Registry


class RetentionService:
    def __init__(
        self,
        events: EventRepository,
        changes: ChangeRepository,
        *,
        retention_days: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._events = events
        self._changes = changes
        self._retention_days = retention_days
        self._clock = clock

    def purge(self) -> dict[str, int]:
        before = self._clock() - timedelta(days=self._retention_days)
        return {"changes": self._changes.purge(before), "events": self._events.purge(before)}


# a retention period of the privacy policy (section 6), applied by the app owning the data.
# A rule is idempotent, works in batches and, in a dry run, changes nothing.
class RetentionRule(Protocol):
    label: str

    def apply(self, *, now: datetime, dry_run: bool) -> RetentionReport: ...


retention_rules: Registry[RetentionRule] = Registry("retention rules")


class RetentionRunner:
    def __init__(self, rules: Registry[RetentionRule], *, clock: Callable[[], datetime]) -> None:
        self._rules = rules
        self._clock = clock

    def names(self) -> list[str]:
        return list(self._rules)

    def run(self, name: str, *, dry_run: bool) -> RetentionReport:
        return self._rules.create(name).apply(now=self._clock(), dry_run=dry_run)


# deletes, batch by batch, the rows past their retention period. `fetch(after_id)` returns the
# next candidates by ascending id, `keep` the ids among them that must stay after all, and
# `delete(ids)` removes them again checking the period, returning how many went.
def purge_expired[E: Expired](
    *,
    rule: str,
    label: str,
    fetch: Callable[[int], Sequence[E]],
    delete: Callable[[list[int]], int],
    dry_run: bool,
    keep: Callable[[Sequence[E]], Collection[int]] | None = None,
) -> RetentionReport:
    samples = SampleCollector(enabled=dry_run)
    affected = 0
    for batch in in_batches(fetch, key=lambda row: row.id):
        kept = keep(batch) if keep else ()
        due = [row for row in batch if row.id not in kept]
        for row in due:
            samples.add(row.description)
        if dry_run:
            affected += len(due)
        elif due:
            with transaction.atomic():
                affected += delete([row.id for row in due])
    return RetentionReport(
        rule=rule, label=label, affected=affected, dry_run=dry_run, samples=samples.samples
    )

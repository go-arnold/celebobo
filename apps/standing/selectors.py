from collections.abc import Callable
from datetime import datetime

from django.db.models import QuerySet

from apps.standing.domain.errors import SanctionNotFound
from apps.standing.domain.read_models import SanctionView
from apps.standing.domain.rules import SanctionKind, SanctionStatus
from apps.standing.models import Sanction


class SanctionSelector:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def page(
        self, *, reseller_id: int | None, status: SanctionStatus | None, offset: int, limit: int
    ) -> tuple[list[SanctionView], int]:
        rows: QuerySet[Sanction] = Sanction.objects.select_related("reseller")
        if reseller_id is not None:
            rows = rows.filter(reseller_id=reseller_id)
        if status is not None:
            rows = rows.filter(status=status.value)
        now = self._clock()
        return [view(row, now) for row in rows[offset : offset + limit]], rows.count()

    def of_reseller(self, reseller_id: int, *, limit: int = 20) -> list[SanctionView]:
        now = self._clock()
        rows = Sanction.objects.select_related("reseller").filter(reseller_id=reseller_id)
        return [view(row, now) for row in rows[:limit]]

    def one(self, sanction_id: int, *, reseller_id: int | None = None) -> SanctionView:
        rows = Sanction.objects.select_related("reseller").filter(pk=sanction_id)
        if reseller_id is not None:
            rows = rows.filter(reseller_id=reseller_id)
        row = rows.first()
        if row is None:
            raise SanctionNotFound
        return view(row, self._clock())


def view(row: Sanction, now: datetime) -> SanctionView:
    reseller = row.reseller
    name = " ".join(filter(None, (reseller.first_name, reseller.last_name))) or reseller.email
    return SanctionView(
        id=row.pk,
        reseller_id=row.reseller_id,
        reseller_name=name,
        kind=SanctionKind(row.kind),
        reason=row.reason,
        urgent=row.urgent,
        days=row.days,
        status=SanctionStatus(row.status),
        explain_until=row.explain_until,
        explanation=row.explanation,
        explained_at=row.explained_at,
        decision_note=row.decision_note,
        decided_at=row.decided_at,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        created_at=row.created_at,
        active=(
            row.status == SanctionStatus.APPLIED.value
            and row.ends_at is not None
            and row.ends_at > now
        ),
    )

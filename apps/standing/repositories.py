from collections.abc import Iterable
from datetime import datetime
from typing import Any

from apps.cash.domain.rules import Level
from apps.standing.domain.rules import SanctionKind, SanctionStatus
from apps.standing.models import ResellerLevel, Sanction


class StandingRepository:
    def levels(self, reseller_ids: Iterable[int]) -> dict[int, Level]:
        ids = list(reseller_ids)
        found = dict(
            ResellerLevel.objects.filter(reseller_id__in=ids).values_list("reseller_id", "level")
        )
        return {pk: Level(found.get(pk, Level.BEGINNER.value)) for pk in ids}

    def level_record(self, reseller_id: int, *, for_update: bool = False) -> ResellerLevel:
        rows = ResellerLevel.objects.select_for_update() if for_update else ResellerLevel.objects
        record = rows.filter(reseller_id=reseller_id).first()
        if record is None:
            record = ResellerLevel.objects.create(reseller_id=reseller_id)
        return record

    def save(self, record: ResellerLevel, *, fields: Iterable[str]) -> None:
        record.save(update_fields=[*fields])

    def create_sanction(self, **fields: Any) -> Sanction:
        return Sanction.objects.create(**fields)

    def sanction(self, sanction_id: int, *, for_update: bool = False) -> Sanction | None:
        rows = Sanction.objects.select_for_update() if for_update else Sanction.objects
        return rows.filter(pk=sanction_id).first()

    def save_sanction(self, sanction: Sanction, *, fields: Iterable[str]) -> None:
        sanction.save(update_fields=[*fields])

    # applied suspensions still running, the latest end per reseller
    def suspended_until(self, reseller_ids: Iterable[int], now: datetime) -> dict[int, datetime]:
        rows = Sanction.objects.filter(
            reseller_id__in=list(reseller_ids),
            kind=SanctionKind.SUSPENSION.value,
            status=SanctionStatus.APPLIED.value,
            ends_at__gt=now,
        ).values_list("reseller_id", "ends_at")
        until: dict[int, datetime] = {}
        for reseller_id, ends_at in rows:
            if ends_at is not None and (reseller_id not in until or ends_at > until[reseller_id]):
                until[reseller_id] = ends_at
        return until

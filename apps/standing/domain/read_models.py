from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.cash.domain.rules import Level
from apps.standing.domain.rules import SanctionKind, SanctionStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class SanctionView:
    id: int
    reseller_id: int
    reseller_name: str
    kind: SanctionKind
    reason: str
    urgent: bool
    days: int | None
    status: SanctionStatus
    explain_until: datetime | None
    explanation: str
    explained_at: datetime | None
    decision_note: str
    decided_at: datetime | None
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
    # a suspension still running
    active: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class Standing:
    reseller_id: int
    reseller_name: str
    level: Level
    advantages: str
    sales: Decimal
    rating: Decimal | None
    reviewed_at: datetime | None
    # what the next level needs (none at the top)
    next_level: Level | None
    next_sales: Decimal | None
    next_rating: Decimal | None
    suspended_until: datetime | None
    sanctions: tuple[SanctionView, ...] = ()

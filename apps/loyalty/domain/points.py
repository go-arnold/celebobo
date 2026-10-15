from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PointBalance:
    total: int
    available: int
    pending: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PointTransactionView:
    id: int
    points: int
    reason: str
    rule_id: int | None
    rule_name: str | None
    reference_type: str | None
    reference_id: str | None
    created_at: datetime

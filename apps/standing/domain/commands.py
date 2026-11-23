from dataclasses import dataclass

from apps.standing.domain.rules import SanctionKind


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenSanction:
    reseller_id: int
    kind: SanctionKind
    reason: str
    # suspension: 7 to 30 days
    days: int | None = None
    # money diverted: applied at once, without waiting for an explanation
    urgent: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ExplainSanction:
    explanation: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DecideSanction:
    apply: bool
    note: str = ""

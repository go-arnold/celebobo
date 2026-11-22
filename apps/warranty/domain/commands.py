from dataclasses import dataclass
from decimal import Decimal

from apps.warranty.domain.rules import ClaimKind, Outcome, ReturnMethod


@dataclass(frozen=True, slots=True, kw_only=True)
class SubmitClaim:
    order_id: int
    item_id: int
    kind: ClaimKind
    description: str
    serial: str = ""
    # photos of the defect (uploaded first, as for message attachments)
    photos: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class AnswerClaim:
    """How the client brings the product back (within 72 hours of the claim)."""

    return_method: ReturnMethod
    note: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ReceiveClaim:
    # for a product taken back sealed only: was the seal intact?
    sealed: bool | None = None
    note: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class DiagnoseClaim:
    covered: bool
    outcome: Outcome
    note: str = ""
    # exchange: the serial of the unit given in place of the old one
    new_serial: str = ""
    # not covered: an optional quote for a paid repair
    quote: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class FinishRepair:
    note: str = ""

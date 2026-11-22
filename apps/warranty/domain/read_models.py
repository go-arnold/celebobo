from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from apps.warranty.domain.rules import ClaimKind, ClaimStatus, Outcome, Protection, ReturnMethod


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimableKinds:
    """For the claim form: which kinds the line can still be claimed for, and until when."""

    order_id: int
    item_id: int
    name: str
    serials: tuple[str, ...]
    kinds: tuple[ClaimKind, ...]
    trial_until: date | None
    warranty_until: date | None
    authenticity_until: date
    open_claim_id: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimView:
    id: int
    number: str
    order_id: int
    order_number: str
    item_id: int
    product_name: str
    serial: str
    client_id: int
    client_name: str
    kind: ClaimKind
    protection: Protection
    description: str
    photos: tuple[str, ...]
    status: ClaimStatus
    created_at: datetime
    answer_due: datetime
    return_method: ReturnMethod | None
    answer_note: str
    answered_at: datetime | None
    received_at: datetime | None
    sealed: bool | None
    diagnosis_due: datetime | None
    covered: bool | None
    outcome: Outcome | None
    diagnosis_note: str
    diagnosed_at: datetime | None
    outcome_due: datetime | None
    new_serial: str
    quote: Decimal | None
    exchange_warranty_until: date | None
    repaired_at: datetime | None
    closed_at: datetime | None
    # a deadline passed while the claim waits for that step
    overdue: bool

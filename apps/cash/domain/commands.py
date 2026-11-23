from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordRemittance:
    reseller_id: int
    amount: Decimal
    reference: str = ""
    received_at: datetime | None = None

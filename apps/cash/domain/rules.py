"""Cash a reseller collects from clients (reseller policy, section 6): it belongs to Celebobo
until remitted, in full, by Mobile Money within 24 hours; the cash a reseller may hold is capped by
their level (section 9). A late remittance, or the cap reached, stops new orders until settled."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

REMIT_HOURS = 24
ZERO = Decimal("0.00")


class Level(StrEnum):
    BEGINNER = "debutant"
    CONFIRMED = "confirme"
    AMBASSADOR = "ambassadeur"

    @property
    def label(self) -> str:
        return LEVEL_LABELS[self]

    @property
    def cash_cap(self) -> Decimal:
        return CASH_CAPS[self]


LEVEL_LABELS = {
    Level.BEGINNER: "Débutant",
    Level.CONFIRMED: "Confirmé",
    Level.AMBASSADOR: "Ambassadeur",
}

# unremitted cash a reseller may hold, by level (reseller policy, section 9)
CASH_CAPS = {
    Level.BEGINNER: Decimal("300.00"),
    Level.CONFIRMED: Decimal("1000.00"),
    Level.AMBASSADOR: Decimal("2500.00"),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CashPosition:
    reseller_id: int
    level: Level
    cap: Decimal
    # collected and not remitted yet
    held: Decimal
    # past its 24 hours and still not remitted
    overdue: Decimal
    oldest_due: datetime | None

    @property
    def blocked_reason(self) -> str | None:
        if self.overdue > 0:
            return f"{self.overdue} $ à reverser depuis plus de {REMIT_HOURS} heures"
        if self.held >= self.cap:
            return f"plafond de {self.cap} $ atteint ({self.held} $ à reverser)"
        return None

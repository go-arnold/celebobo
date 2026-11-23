"""Reseller levels and sanctions (reseller policy, sections 9 and 10)."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from apps.cash.domain.rules import Level

# the level is reviewed each quarter, from the validated sales of the last 3 months and the rating
REVIEW_MONTHS = (1, 4, 7, 10)
SALES_MONTHS = 3
VALIDATION_DAYS = 7


@dataclass(frozen=True, slots=True)
class Threshold:
    level: Level
    sales: Decimal
    rating: Decimal


# highest first: the first one met is the level
THRESHOLDS = (
    Threshold(Level.AMBASSADOR, Decimal("3000.00"), Decimal("4.5")),
    Threshold(Level.CONFIRMED, Decimal("1000.00"), Decimal("4.0")),
)

ADVANTAGES = {
    Level.BEGINNER: "Commandes de sa zone. Plafond d'argent non reversé : 300 $",
    Level.CONFIRMED: (
        "Priorité sur les commandes de sa zone. Plafond : 1 000 $. Produit de démonstration prêté"
    ),
    Level.AMBASSADOR: "Accès anticipé aux promotions. Plafond : 2 500 $. Mise en avant sur le site",
}


def level_for(sales: Decimal, rating: Decimal | None) -> Level:
    """Without any rating yet, a reseller stays a beginner."""
    for threshold in THRESHOLDS:
        if sales >= threshold.sales and rating is not None and rating >= threshold.rating:
            return threshold.level
    return Level.BEGINNER


def is_review_day(day: date) -> bool:
    return day.day == 1 and day.month in REVIEW_MONTHS


def months_before(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 - months
    year, month = moment.year + month // 12, month % 12 + 1
    return moment.replace(
        year=year, month=month, day=min(moment.day, calendar.monthrange(year, month)[1])
    )


# section 10: warning, suspension of 7 to 30 days without new orders, immediate exclusion; before a
# suspension or an exclusion the reseller is told in writing and may explain within 48 hours,
# unless it is urgent (money diverted)
EXPLAIN_HOURS = 48
SUSPENSION_DAYS = (7, 30)


class SanctionKind(StrEnum):
    WARNING = "warning"
    SUSPENSION = "suspension"
    EXCLUSION = "exclusion"

    @property
    def label(self) -> str:
        return KIND_LABELS[self]

    @property
    def needs_hearing(self) -> bool:
        return self is not SanctionKind.WARNING


KIND_LABELS = {
    SanctionKind.WARNING: "Avertissement écrit",
    SanctionKind.SUSPENSION: "Suspension",
    SanctionKind.EXCLUSION: "Exclusion",
}


class SanctionStatus(StrEnum):
    # told in writing: the reseller may explain until `explain_until`
    NOTIFIED = "notified"
    APPLIED = "applied"
    DROPPED = "dropped"

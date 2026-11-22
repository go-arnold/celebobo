"""Warranty claims (warranty policy, "Comment faire une réclamation"): which protection covers a
claim, the steps and their deadlines."""

import calendar
from datetime import date, datetime, timedelta
from enum import StrEnum

# the 7-day trial (art. 59), the one-month CeLE BoBO warranty, both from the delivery; the
# authenticity guarantee, 12 months from the purchase
TRIAL_DAYS = 7
WARRANTY_MONTHS = 1
AUTHENTICITY_MONTHS = 12
# answer within 72 hours (art. 65), diagnosis within 3 working days of the reception, repair within
# 10 working days, refund within 15 days (art. 59); an exchanged product keeps the warranty left on
# the old one, 15 days at least
ANSWER_HOURS = 72
DIAGNOSIS_WORKING_DAYS = 3
REPAIR_WORKING_DAYS = 10
REFUND_DAYS = 15
EXCHANGE_MIN_DAYS = 15
SUNDAY = 6


class ClaimKind(StrEnum):
    # faulty, or different from the order; during the trial or the warranty
    DEFECT = "defect"
    # the product does not suit the client: during the trial only
    CHANGE_OF_MIND = "change_of_mind"
    # a counterfeit: within 12 months of the purchase
    COUNTERFEIT = "counterfeit"

    @property
    def label(self) -> str:
        return KIND_LABELS[self]


KIND_LABELS = {
    ClaimKind.DEFECT: "Produit défectueux ou non conforme",
    ClaimKind.CHANGE_OF_MIND: "Le produit ne me convient pas",
    ClaimKind.COUNTERFEIT: "Produit contrefait",
}


class Protection(StrEnum):
    TRIAL = "trial"
    WARRANTY = "warranty"
    AUTHENTICITY = "authenticity"


class ReturnMethod(StrEnum):
    # left at the shop, avenue Mwanga n° 21, Bukavu
    SHOP = "shop"
    # picked up by the client's reseller
    RESELLER = "reseller"


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    # the client knows how to bring the product back
    ANSWERED = "answered"
    # the product is in: a drop-off slip is issued
    RECEIVED = "received"
    # being repaired
    REPAIRING = "repairing"
    # outcome applied (refund recorded, product exchanged, repaired or given back)
    CLOSED = "closed"


OPEN_STATUSES = frozenset(
    {ClaimStatus.SUBMITTED, ClaimStatus.ANSWERED, ClaimStatus.RECEIVED, ClaimStatus.REPAIRING}
)


class Outcome(StrEnum):
    REPAIR = "repair"
    EXCHANGE = "exchange"
    REFUND = "refund"
    # not covered (or a change of mind on an opened sealed-only product): given back, maybe with a
    # quote for a paid repair
    NOT_COVERED = "not_covered"


def add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def add_working_days(moment: datetime, days: int) -> datetime:
    """Monday to Saturday are working days (owner, 18 Nov 2026)."""
    current = moment
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() != SUNDAY:
            days -= 1
    return current


def protection_for(
    kind: ClaimKind,
    *,
    ordered_on: date,
    delivered_on: date | None,
    today: date,
    extension_days: int = 0,
) -> Protection | None:
    """The protection that covers this claim today, or None when its window is closed. A repair
    extends the warranty by the time it took (`extension_days`)."""
    if kind is ClaimKind.COUNTERFEIT:
        return (
            Protection.AUTHENTICITY
            if today <= add_months(ordered_on, AUTHENTICITY_MONTHS)
            else None
        )
    if delivered_on is None:
        return None
    if today <= delivered_on + timedelta(days=TRIAL_DAYS):
        return Protection.TRIAL
    if kind is ClaimKind.DEFECT and today <= add_months(delivered_on, WARRANTY_MONTHS) + timedelta(
        days=extension_days
    ):
        return Protection.WARRANTY
    return None


def outcomes_for(kind: ClaimKind, *, covered: bool) -> frozenset[Outcome]:
    if not covered:
        return frozenset({Outcome.NOT_COVERED})
    if kind is ClaimKind.CHANGE_OF_MIND:
        # an exchange (store credit comes with step 7.3); the client pays the return
        return frozenset({Outcome.EXCHANGE})
    if kind is ClaimKind.COUNTERFEIT:
        return frozenset({Outcome.REFUND})
    return frozenset({Outcome.REPAIR, Outcome.EXCHANGE, Outcome.REFUND})


def exchange_warranty_until(warranty_until: date, today: date) -> date:
    return max(warranty_until, today + timedelta(days=EXCHANGE_MIN_DAYS))


SHOP_ADDRESS = "avenue Mwanga n° 21, Nyalukemba, Bukavu"


def client_message(
    status: ClaimStatus,
    outcome: Outcome | None,
    *,
    number: str,
    return_method: ReturnMethod | None = None,
    note: str = "",
    quote: str | None = None,
) -> str:
    """What the client is told at each step of a claim."""
    if status is ClaimStatus.ANSWERED:
        how = (
            f"Déposez le produit au {SHOP_ADDRESS}, avec sa facture."
            if return_method is ReturnMethod.SHOP
            else "Votre revendeur vient reprendre le produit."
        )
        text = f"Nous avons étudié votre réclamation. {how}"
    elif status is ClaimStatus.RECEIVED:
        text = (
            f"Produit reçu : votre bon de dépôt est le {number}. Diagnostic sous 3 jours ouvrables."
        )
    elif status is ClaimStatus.REPAIRING:
        text = "Diagnostic fait : votre produit est en réparation, sous 10 jours ouvrables."
    elif outcome is Outcome.REFUND:
        text = (
            "Remboursement accordé : vous êtes remboursé sous 15 jours, par le même moyen de "
            "paiement."
        )
    elif outcome is Outcome.EXCHANGE:
        text = "Échange accordé : votre nouveau produit vous attend."
    elif outcome is Outcome.REPAIR:
        text = (
            "Réparation terminée : votre produit vous attend. Sa garantie est prolongée du temps "
            "passé en réparation."
        )
    else:
        text = "Le problème n'est pas couvert par la garantie : le produit vous est rendu."
        if quote:
            text += f" Devis pour une réparation payante : {quote} $."
    return f"{text} {note}".strip() if note else text

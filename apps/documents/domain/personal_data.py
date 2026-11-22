"""The personal data export ("Télécharger mes données", privacy policy art. 211).

The JSON file is the reference: stable English keys, ISO 8601 dates, money as strings with two
decimals. The HTML file shows the same content in French.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType

from core.domain.actor import Role

FORMAT_NAME = "celebobo.personal-data"
FORMAT_VERSION = 1

JSON_NAME = "mes-donnees.json"
HTML_NAME = "mes-donnees.html"
README_NAME = "LISEZMOI.txt"

# the sections of the file, in this order; a section with nothing to show is left out
SECTION_ORDER = (
    "account",
    "notification_preferences",
    # consent records (step 6.1) plug in here: register a collector under this key
    "consents",
    "orders",
    "points",
    "reviews",
    "favorites",
    "messages",
    "reseller_applications",
    "reseller",
)

SECTION_TITLES = MappingProxyType(
    {
        "account": "Compte",
        "notification_preferences": "Préférences de notification",
        "consents": "Consentements",
        "orders": "Commandes",
        "points": "Points de fidélité",
        "reviews": "Avis publiés",
        "favorites": "Favoris",
        "messages": "Discussions",
        "reseller_applications": "Candidatures revendeur",
        "reseller": "Activité de revendeur",
    }
)


@dataclass(frozen=True, slots=True)
class DataSubject:
    """The person whose data is exported: always the owner of the request."""

    user_id: int
    role: Role


def ordered_sections(keys: list[str]) -> list[str]:
    known = [key for key in SECTION_ORDER if key in keys]
    return known + sorted(key for key in keys if key not in SECTION_ORDER)


def money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def instant(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()

"""Consents the privacy policy asks for (Code du numérique art. 68-70, 192, 196 and 202).

Each consent is recorded with the version of the document accepted and the date, as proof. The
required ones (terms and hosting abroad) must be valid for the current version of their document,
otherwise the account must accept them again before it can be used.
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from core.domain.actor import Role


class ConsentKind(StrEnum):
    # conditions of sale and processing of personal data (policy §3)
    TERMS = "terms"
    # express consent to the hosting of the data outside the DRC (policy §5, art. 202)
    HOSTING_ABROAD = "hosting_abroad"
    # commercial offers by SMS, WhatsApp or e-mail (policy §8, art. 68-70): optional
    MARKETING = "marketing"

    @property
    def label(self) -> str:
        return CONSENT_LABELS[self]

    @property
    def required(self) -> bool:
        return self in REQUIRED_CONSENTS


class ConsentSource(StrEnum):
    SIGNUP = "signup"
    # reserved for a consent asked on the checkout page (none yet)
    CHECKOUT = "checkout"
    ACCOUNT = "account"
    # the completion step right after a Google sign-up
    GOOGLE = "google"


CONSENT_LABELS: Mapping[ConsentKind, str] = MappingProxyType(
    {
        ConsentKind.TERMS: (
            "Conditions générales de vente et traitement de mes données personnelles"
        ),
        ConsentKind.HOSTING_ABROAD: "Hébergement de mes données hors de RDC",
        ConsentKind.MARKETING: "Offres commerciales par SMS, WhatsApp ou e-mail",
    }
)

REQUIRED_CONSENTS: tuple[ConsentKind, ...] = (ConsentKind.TERMS, ConsentKind.HOSTING_ABROAD)

# the document each consent is given on: its version is recorded with the consent, and a new
# version of that page asks for the consent again. `terms` is given on the conditions of sale; the
# hosting abroad (§5) and the commercial offers (§8) on the privacy policy.
PRIVACY_POLICY = "politique-de-confidentialite"
CONDITIONS_OF_SALE = "conditions-de-vente"
CONSENT_DOCUMENTS: Mapping[ConsentKind, str] = MappingProxyType(
    {
        ConsentKind.TERMS: CONDITIONS_OF_SALE,
        ConsentKind.HOSTING_ABROAD: PRIVACY_POLICY,
        ConsentKind.MARKETING: PRIVACY_POLICY,
    }
)

# staff accounts (managers, admins) are Celebobo's own team and do not sign up on the site
CONSENT_ROLES = frozenset({Role.CLIENT, Role.RESELLER})


class PolicyVersions(Protocol):
    """Current version of the document of each consent ("" when the document has no version)."""

    def current(self) -> Mapping[ConsentKind, str]: ...


def needs_consents(role: Role) -> bool:
    return role in CONSENT_ROLES


def missing_consents(
    role: Role, accepted: Mapping[ConsentKind, str], current: Mapping[ConsentKind, str]
) -> tuple[ConsentKind, ...]:
    """Required consents the account still has to give.

    `accepted` maps each consent the account has not withdrawn to the version it accepted last. A
    required consent accepted on an older version of its document must be accepted again; a
    document without a version accepts any.
    """
    if not needs_consents(role):
        return ()
    return tuple(
        kind
        for kind in REQUIRED_CONSENTS
        if kind not in accepted or (current.get(kind, "") not in ("", accepted[kind]))
    )


def unaccepted_required(kinds: Iterable[ConsentKind]) -> tuple[ConsentKind, ...]:
    given = set(kinds)
    return tuple(kind for kind in REQUIRED_CONSENTS if kind not in given)

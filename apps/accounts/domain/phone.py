"""Phone numbers of the DRC, stored in E.164: +243 followed by the 9 digits of the national number.

Accepted inputs: `+243 81 234 5678`, `00243812345678`, `243812345678`, `0812345678`, `812345678`,
with any spaces, dots, dashes or parentheses, and with the trunk `0` kept after the country code
(`+243 0812345678`, `+243 (0)81 234 5678`). Only ASCII digits count: Arabic-Indic or fullwidth
digits are refused, so one number has a single stored form. Only mobile numbers are accepted
(national number starting with 8 or 9: Vodacom, Airtel, Orange, Africell): the site reaches its
clients by SMS, WhatsApp and calls, and the DRC has practically no fixed lines left.
"""

import re

from apps.accounts.domain.consents import CONSENT_ROLES
from apps.accounts.domain.errors import InvalidPhone
from core.domain.actor import Role

COUNTRY_CODE = "243"
_SEPARATORS = re.compile(r"[\s.()\-]")
_NATIONAL = re.compile(r"[89][0-9]{8}")
_ASCII_DIGITS = re.compile(r"[0-9]+")
_COUNTRY_PREFIXES = ("+243", "00243", "243")


def _national_part(raw: str) -> str:
    """`raw` without separators, country code and trunk `0`: the national number when valid."""
    digits = _SEPARATORS.sub("", raw.strip())
    for prefix in _COUNTRY_PREFIXES:
        if digits.startswith(prefix):
            digits = digits[len(prefix) :]
            break
    return digits.removeprefix("0")


def parse_drc_phone(raw: str) -> str | None:
    """The E.164 form of `raw`, or None when it is not a DRC mobile number."""
    national = _national_part(raw)
    return f"+{COUNTRY_CODE}{national}" if _NATIONAL.fullmatch(national) else None


def phone_search_fragment(term: str) -> str | None:
    """The part of a stored number (+243…) that a partial number typed in a search matches.

    `081234` → `81234`, `+243 81 2` → `812`; None when `term` is not made of digits.
    """
    fragment = _national_part(term)
    return fragment if _ASCII_DIGITS.fullmatch(fragment) else None


def normalize_drc_phone(raw: str | None) -> str | None:
    """E.164 form of a phone number; None when empty; `InvalidPhone` when not a DRC mobile."""
    if raw is None or not raw.strip():
        return None
    phone = parse_drc_phone(raw)
    if phone is None:
        raise InvalidPhone
    return phone


def phone_required(role: Role) -> bool:
    """Clients and resellers need a phone number (delivery, payment, WhatsApp); staff do not."""
    return role in CONSENT_ROLES


def phone_missing(role: Role, phone: str | None) -> bool:
    return phone_required(role) and not phone

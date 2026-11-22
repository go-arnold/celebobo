"""Phone numbers of the DRC, stored in E.164: +243 followed by the 9 digits of the national number.

Accepted inputs: `+243 81 234 5678`, `00243812345678`, `243812345678`, `0812345678`, `812345678`,
with any spaces, dots, dashes or parentheses. Only mobile numbers are accepted (national number
starting with 8 or 9: Vodacom, Airtel, Orange, Africell): the site reaches its clients by SMS,
WhatsApp and calls, and the DRC has practically no fixed lines left.
"""

import re

from apps.accounts.domain.consents import CONSENT_ROLES
from apps.accounts.domain.errors import InvalidPhone
from core.domain.actor import Role

COUNTRY_CODE = "243"
_SEPARATORS = re.compile(r"[\s.()\-]")
_NATIONAL = re.compile(r"[89]\d{8}")
_PREFIXES = ("+243", "00243", "243", "0")


def parse_drc_phone(raw: str) -> str | None:
    """The E.164 form of `raw`, or None when it is not a DRC mobile number."""
    digits = _SEPARATORS.sub("", raw.strip())
    for prefix in _PREFIXES:
        if digits.startswith(prefix) and _NATIONAL.fullmatch(digits[len(prefix) :]):
            return f"+{COUNTRY_CODE}{digits[len(prefix) :]}"
    return f"+{COUNTRY_CODE}{digits}" if _NATIONAL.fullmatch(digits) else None


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

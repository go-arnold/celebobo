import re

from apps.accounts.domain.phone import normalize_drc_phone

_WHITESPACE = re.compile(r"\s+")


def normalize_email(email: str) -> str:
    return email.strip().lower()


# E.164 (+243…) or None when empty; raises InvalidPhone for anything else
def normalize_phone(phone: str | None) -> str | None:
    return normalize_drc_phone(phone)


def clean_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()

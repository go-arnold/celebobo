import re

_WHITESPACE = re.compile(r"\s+")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    cleaned = _WHITESPACE.sub(" ", phone).strip()
    return cleaned or None


def clean_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()

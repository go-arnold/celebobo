import secrets

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PREFIX = "CB"
LENGTH = 8


def new_order_number() -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    return f"{PREFIX}-{body[:4]}-{body[4:]}"


def normalize_order_number(raw: str) -> str:
    return raw.strip().upper()

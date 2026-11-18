"""The delivery code: the client hands it to the reseller once they have their order in hand."""

import secrets

CODE_LENGTH = 6
# wrong codes before the code locks; staff are alerted and confirm the delivery themselves
MAX_ATTEMPTS = 5


def new_code() -> str:
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def matches(expected: str, given: str) -> bool:
    return bool(expected) and secrets.compare_digest(expected, given.strip())

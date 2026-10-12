import re

HERO = "hero"
FIXED_PLACEMENTS = frozenset({HERO, "hero_mini", "hero_side", "deal_side"})
# one slot per home block or column, named after its category: "showcase:smartphones"
SECTION_PLACEMENTS = frozenset({"showcase", "column"})
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_PLACEMENT_LENGTH = 140


def valid_placement(value: str) -> bool:
    if value in FIXED_PLACEMENTS:
        return True
    kind, _, slug = value.partition(":")
    return (
        kind in SECTION_PLACEMENTS
        and len(value) <= MAX_PLACEMENT_LENGTH
        and _SLUG.fullmatch(slug) is not None
    )

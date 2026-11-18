"""Failed deliveries: the reseller tries on two working days, then the order is cancelled."""

from collections.abc import Iterable
from datetime import date

# failed attempts on this many different working days cancel the order (delivery policy)
ATTEMPT_DAYS = 2
SUNDAY = 6


def working_days(days: Iterable[date]) -> int:
    """How many different working days (Monday to Saturday) these attempts fall on."""
    return len({day for day in days if day.weekday() != SUNDAY})

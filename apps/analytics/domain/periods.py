from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum

MAX_DAILY_SPAN = timedelta(days=92)


class Period(StrEnum):
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"
    YEAR = "12m"
    YEAR_TO_DATE = "ytd"


class Granularity(StrEnum):
    DAY = "day"
    MONTH = "month"


@dataclass(frozen=True, slots=True)
class Window:
    start: datetime
    end: datetime
    granularity: Granularity

    @property
    def span(self) -> timedelta:
        return self.end - self.start

    def previous(self) -> "Window":
        return Window(self.start - self.span, self.start, self.granularity)

    def buckets(self) -> list[date]:
        first = self.start.date()
        last = (self.end - timedelta(microseconds=1)).date()
        if self.granularity is Granularity.MONTH:
            return _months(first.replace(day=1), last)
        return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def window_for(
    now: datetime,
    *,
    period: Period | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Window:
    if date_from is not None or date_to is not None:
        return _custom(now, date_from, date_to)
    today = _midnight(now, now.date())
    match period or Period.MONTH:
        case Period.WEEK:
            return Window(today - timedelta(days=6), now, Granularity.DAY)
        case Period.MONTH:
            return Window(today - timedelta(days=29), now, Granularity.DAY)
        case Period.QUARTER:
            return Window(today - timedelta(days=89), now, Granularity.DAY)
        case Period.YEAR:
            start = _shift_months(now.date().replace(day=1), -11)
            return Window(_midnight(now, start), now, Granularity.MONTH)
        case Period.YEAR_TO_DATE:
            return Window(_midnight(now, date(now.year, 1, 1)), now, Granularity.MONTH)


def change_rate(current: Decimal, previous: Decimal) -> float | None:
    if not previous:
        return None
    return round(float((current - previous) / previous * 100), 1)


def _custom(now: datetime, date_from: date | None, date_to: date | None) -> Window:
    last = date_to or now.date()
    first = date_from or last - timedelta(days=29)
    start = _midnight(now, first)
    end = min(_midnight(now, last + timedelta(days=1)), now)
    granularity = Granularity.DAY if end - start <= MAX_DAILY_SPAN else Granularity.MONTH
    return Window(start, end, granularity)


def _midnight(reference: datetime, day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=reference.tzinfo)


def _shift_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _months(first: date, last: date) -> list[date]:
    months = []
    current = first
    while current <= last:
        months.append(current)
        current = _shift_months(current, 1)
    return months

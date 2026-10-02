from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.analytics.domain.periods import Granularity, Period, change_rate, window_for

KINSHASA = ZoneInfo("Africa/Kinshasa")
NOW = datetime(2026, 3, 15, 14, 30, tzinfo=KINSHASA)


@pytest.mark.parametrize(
    ("period", "start", "granularity", "buckets"),
    [
        (Period.WEEK, datetime(2026, 3, 9, tzinfo=KINSHASA), Granularity.DAY, 7),
        (Period.MONTH, datetime(2026, 2, 14, tzinfo=KINSHASA), Granularity.DAY, 30),
        (Period.QUARTER, datetime(2025, 12, 16, tzinfo=KINSHASA), Granularity.DAY, 90),
        (Period.YEAR, datetime(2025, 4, 1, tzinfo=KINSHASA), Granularity.MONTH, 12),
        (Period.YEAR_TO_DATE, datetime(2026, 1, 1, tzinfo=KINSHASA), Granularity.MONTH, 3),
    ],
)
def test_preset_windows(period, start, granularity, buckets):
    window = window_for(NOW, period=period)

    assert window.start == start
    assert window.end == NOW
    assert window.granularity is granularity
    assert len(window.buckets()) == buckets


def test_default_is_thirty_days():
    assert window_for(NOW) == window_for(NOW, period=Period.MONTH)


def test_previous_window_has_the_same_length():
    window = window_for(NOW, period=Period.WEEK)
    previous = window.previous()

    assert previous.end == window.start
    assert previous.span == window.span


def test_custom_ranges():
    past = window_for(NOW, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    long = window_for(NOW, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    open_ended = window_for(NOW, date_from=date(2026, 3, 10))

    assert past.end == datetime(2026, 2, 1, tzinfo=KINSHASA)
    assert past.granularity is Granularity.DAY
    assert long.granularity is Granularity.MONTH
    assert len(long.buckets()) == 12
    assert open_ended.end == NOW
    assert open_ended.buckets()[-1] == date(2026, 3, 15)
    assert window_for(NOW, date_to=date(2026, 3, 1)).span == timedelta(days=30)


def test_change_rate():
    assert change_rate(Decimal(150), Decimal(100)) == 50.0
    assert change_rate(Decimal(50), Decimal(200)) == -75.0
    assert change_rate(Decimal(10), Decimal(0)) is None

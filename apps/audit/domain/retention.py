import calendar
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime

# rows handled per transaction by every retention rule
BATCH_SIZE = 200
# how many affected rows a dry run lists
SAMPLE_LIMIT = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class RetentionReport:
    rule: str
    label: str
    affected: int
    dry_run: bool
    # in a dry run, a short description of the first rows that would be affected
    samples: tuple[str, ...] = ()


def years_before(moment: datetime, years: int) -> datetime:
    year = moment.year - years
    day = min(moment.day, calendar.monthrange(year, moment.month)[1])
    return moment.replace(year=year, day=day)


class SampleCollector:
    def __init__(self, *, enabled: bool, limit: int = SAMPLE_LIMIT) -> None:
        self._enabled = enabled
        self._limit = limit
        self._samples: list[str] = []

    def add(self, description: str) -> None:
        if self._enabled and len(self._samples) < self._limit:
            self._samples.append(description)

    @property
    def samples(self) -> tuple[str, ...]:
        return tuple(self._samples)


@dataclass(frozen=True, slots=True)
class Expired:
    id: int
    description: str


# walks rows by ascending id, `fetch(after_id)` returning the next batch (empty when done);
# rows kept by a rule are never fetched twice
def in_batches[T](
    fetch: Callable[[int], Sequence[T]], key: Callable[[T], int]
) -> Iterator[Sequence[T]]:
    after = 0
    while batch := fetch(after):
        yield batch
        after = key(batch[-1])

from collections.abc import Callable, Iterable
from typing import Any

from django.core.cache import cache

PENDING_KEY = "content:storefront:pending"
SCHEDULED_KEY = "content:storefront:scheduled"


class PendingTags:
    def __init__(self, *, clock: Callable[[], float], debounce: int, max_wait: int) -> None:
        self._clock = clock
        self._debounce = debounce
        self._max_wait = max_wait

    def add(self, tags: Iterable[str]) -> bool:
        now = self._clock()
        pending = self._pending() or {"tags": [], "first": now}
        pending["tags"] = sorted({*pending["tags"], *tags})
        pending["last"] = now
        cache.set(PENDING_KEY, pending, timeout=self._max_wait * 10)
        return bool(cache.add(SCHEDULED_KEY, 1, timeout=self._max_wait))

    def wait(self) -> int:
        pending = self._pending()
        if not pending:
            return 0
        now = self._clock()
        quiet = pending["last"] + self._debounce - now
        overdue = pending["first"] + self._max_wait - now
        return max(0, int(min(quiet, overdue) + 0.999))

    def drain(self) -> list[str]:
        tags = list((self._pending() or {}).get("tags", []))
        cache.delete_many([PENDING_KEY, SCHEDULED_KEY])
        return tags

    @staticmethod
    def _pending() -> dict[str, Any] | None:
        pending: dict[str, Any] | None = cache.get(PENDING_KEY)
        return pending

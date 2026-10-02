import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

from django.core.cache import caches
from django.core.serializers.json import DjangoJSONEncoder

_MISS = object()


def cache_key(*parts: Any) -> str:
    raw = json.dumps(parts, cls=DjangoJSONEncoder, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class VersionedCache:
    def __init__(self, namespace: str, *, alias: str = "default", ttl: int = 300) -> None:
        self._namespace = namespace
        self._alias = alias
        self._ttl = ttl

    def get_or_set[T](self, key: str, builder: Callable[[], T]) -> T:
        cache = caches[self._alias]
        full_key = f"{self._namespace}:v{self.version()}:{key}"
        value = cache.get(full_key, _MISS)
        if value is _MISS:
            value = builder()
            cache.set(full_key, value, timeout=self._ttl)
        return cast(T, value)

    def version(self) -> int:
        version = caches[self._alias].get_or_set(self._version_key, 1, timeout=None)
        return int(version or 1)

    def bump(self) -> None:
        cache = caches[self._alias]
        try:
            cache.incr(self._version_key)
        except ValueError:
            cache.set(self._version_key, 2, timeout=None)

    @property
    def _version_key(self) -> str:
        return f"{self._namespace}:version"

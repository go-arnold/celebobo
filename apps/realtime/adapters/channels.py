from collections.abc import Iterable, Mapping
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import caches

from apps.realtime.domain.protocol import ServerEvent

BROADCAST_HANDLER = "broadcast"
CLOSE_HANDLER = "session.close"


class ChannelLayerBroadcaster:
    def send(self, groups: Iterable[str], event: ServerEvent, data: Mapping[str, Any]) -> None:
        layer = get_channel_layer()
        if layer is None:
            return
        message = {"type": BROADCAST_HANDLER, "event": event.value, "data": dict(data)}
        _send_to_groups(layer, groups, message)

    def close(self, groups: Iterable[str], *, code: int) -> None:
        layer = get_channel_layer()
        if layer is None:
            return
        _send_to_groups(layer, groups, {"type": CLOSE_HANDLER, "code": code})


def _send_to_groups(layer: Any, groups: Iterable[str], message: dict[str, Any]) -> None:
    for group in dict.fromkeys(groups):
        async_to_sync(layer.group_send)(group, message)


class CachePresenceStore:
    def __init__(self, cache_alias: str = "default") -> None:
        self._cache_alias = cache_alias

    def connect(self, user_id: int, *, ttl: int) -> int:
        cache = caches[self._cache_alias]
        key = self._key(user_id)
        if cache.add(key, 1, timeout=ttl):
            return 1
        count = int(cache.incr(key))
        cache.touch(key, timeout=ttl)
        return count

    def disconnect(self, user_id: int) -> int:
        cache = caches[self._cache_alias]
        key = self._key(user_id)
        try:
            remaining = int(cache.decr(key))
        except ValueError:
            return 0
        if remaining <= 0:
            cache.delete(key)
        return remaining

    def refresh(self, user_id: int, *, ttl: int) -> None:
        cache = caches[self._cache_alias]
        if not cache.touch(self._key(user_id), timeout=ttl):
            cache.add(self._key(user_id), 1, timeout=ttl)

    def online(self, user_ids: Iterable[int]) -> set[int]:
        ids = list(user_ids)
        stored = caches[self._cache_alias].get_many([self._key(user_id) for user_id in ids])
        return {user_id for user_id in ids if int(stored.get(self._key(user_id), 0)) > 0}

    @staticmethod
    def _key(user_id: int) -> str:
        return f"realtime:presence:{user_id}"

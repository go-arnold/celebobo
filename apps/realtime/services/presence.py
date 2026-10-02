from collections.abc import Iterable

from apps.realtime.services.contracts import PresenceStore

DEFAULT_PRESENCE_TTL = 90


class PresenceService:
    def __init__(self, store: PresenceStore, *, ttl: int = DEFAULT_PRESENCE_TTL) -> None:
        self._store = store
        self._ttl = ttl

    def connected(self, user_id: int) -> bool:
        return self._store.connect(user_id, ttl=self._ttl) == 1

    def disconnected(self, user_id: int) -> bool:
        return self._store.disconnect(user_id) <= 0

    def heartbeat(self, user_id: int) -> None:
        self._store.refresh(user_id, ttl=self._ttl)

    def online(self, user_ids: Iterable[int]) -> set[int]:
        return self._store.online(user_ids)

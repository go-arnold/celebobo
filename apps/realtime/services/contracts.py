from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from apps.realtime.domain.protocol import ServerEvent


class Broadcaster(Protocol):
    def send(self, groups: Iterable[str], event: ServerEvent, data: Mapping[str, Any]) -> None: ...


class PresenceStore(Protocol):
    def connect(self, user_id: int, *, ttl: int) -> int: ...

    def disconnect(self, user_id: int) -> int: ...

    def refresh(self, user_id: int, *, ttl: int) -> None: ...

    def online(self, user_ids: Iterable[int]) -> set[int]: ...

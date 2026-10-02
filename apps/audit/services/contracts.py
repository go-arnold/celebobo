from collections.abc import Sequence
from typing import Protocol


class ActorNames(Protocol):
    def names(self, ids: Sequence[int]) -> dict[int, str]: ...

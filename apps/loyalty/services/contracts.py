from typing import Protocol

from apps.loyalty.domain.membership import Requester


class People(Protocol):
    def requester(self, user_id: int) -> Requester: ...

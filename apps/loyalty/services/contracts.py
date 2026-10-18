from typing import Protocol

from apps.loyalty.domain.cashback import Purchase


class People(Protocol):
    def requester(self, user_id: int) -> Purchase: ...


class OrderLedger(Protocol):
    def purchase(self, order_id: int) -> Purchase | None: ...


class ReturnPolicy(Protocol):
    def return_days(self) -> int: ...

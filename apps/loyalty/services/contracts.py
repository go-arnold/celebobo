from datetime import datetime
from decimal import Decimal
from typing import Protocol

from apps.loyalty.domain.points import Purchase, Referral


class OrderLedger(Protocol):
    def purchase(self, order_id: int) -> Purchase | None: ...

    # when the client last placed an order that was not cancelled
    def last_purchase(self, client_id: int) -> datetime | None: ...

    # delivered orders to date: how many, and what they came to
    def delivered(self, client_id: int) -> tuple[int, Decimal]: ...


class ReturnPolicy(Protocol):
    def return_days(self) -> int: ...


class Referrals(Protocol):
    # the active reseller who invited the client, and since when
    def referral(self, client_id: int) -> Referral | None: ...

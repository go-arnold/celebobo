from apps.loyalty.domain.points import PointBalance, PointTransactionView
from apps.loyalty.repositories import PointTransactionRepository
from apps.loyalty.selectors import to_point_transaction_view


class PointService:
    def __init__(self, *, transactions: PointTransactionRepository) -> None:
        self._transactions = transactions

    def balance(self, user_id: int) -> PointBalance:
        rows, _ = self._transactions.for_user(user_id, offset=0, limit=1000)
        total = sum((tx.points for tx in rows), 0)
        return PointBalance(total=total, available=total, pending=0)

    def transactions(
        self, user_id: int, *, offset: int, limit: int
    ) -> tuple[list[PointTransactionView], int]:
        rows, total = self._transactions.for_user(user_id, offset=offset, limit=limit)
        return [to_point_transaction_view(tx) for tx in rows], total

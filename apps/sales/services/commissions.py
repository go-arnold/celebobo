from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from apps.sales.domain.enums import CommissionKind
from apps.sales.domain.payouts import VALIDATION_DAYS
from apps.sales.domain.rules import ZERO, commission_for, proportional_reversal
from apps.sales.models import CommissionEntry, Sale
from apps.sales.repositories import CommissionRepository
from apps.sales.services.contracts import OrderBook, Sellers
from core.domain.actor import Role


@dataclass(frozen=True, slots=True)
class CommissionChange:
    reseller_id: int
    delta: Decimal


class CommissionService:
    def __init__(
        self,
        commissions: CommissionRepository,
        sellers: Sellers,
        *,
        books: OrderBook | None = None,
    ) -> None:
        self._commissions = commissions
        self._sellers = sellers
        self._books = books

    def earn(self, sale: Sale, *, rate: Decimal | None = None) -> CommissionChange | None:
        if rate is None:
            seller = self._sellers.profile(sale.seller_id)
            if seller is None or seller.role is not Role.RESELLER:
                return None
            rate = seller.commission_rate
        amount = commission_for(sale.total, rate)
        if amount <= ZERO:
            return None
        self._entry(
            sale,
            kind=CommissionKind.EARNED,
            rate=rate,
            base=sale.total,
            amount=amount,
            note="Commission sur vente",
        )
        return CommissionChange(sale.seller_id, amount)

    def reverse_refund(
        self, sale: Sale, refunded: Decimal, *, note: str
    ) -> CommissionChange | None:
        earned = self._commissions.net_for_sale(sale)
        rate = self._commissions.earned_rate(sale)
        if rate is None or earned <= ZERO:
            return None
        amount = min(
            proportional_reversal(commission_for(sale.total, rate), refunded, sale.total), earned
        )
        if amount <= ZERO:
            return None
        self._entry(
            sale, kind=CommissionKind.REVERSED, rate=rate, base=refunded, amount=-amount, note=note
        )
        return CommissionChange(sale.seller_id, -amount)

    def void(self, sale: Sale, *, note: str) -> CommissionChange | None:
        net = self._commissions.net_for_sale(sale)
        if net <= ZERO:
            return None
        rate = self._commissions.earned_rate(sale) or Decimal(0)
        self._entry(
            sale, kind=CommissionKind.REVERSED, rate=rate, base=sale.total, amount=-net, note=note
        )
        return CommissionChange(sale.seller_id, -net)

    def rebase(self, sale: Sale) -> list[CommissionChange]:
        rate = self._commissions.earned_rate(sale)
        if rate is None:
            return []
        changes = [change for change in [self.void(sale, note="Vente modifiée")] if change]
        if earned := self.earn(sale, rate=rate):
            changes.append(earned)
        return changes

    def _entry(
        self,
        sale: Sale,
        *,
        kind: CommissionKind,
        rate: Decimal,
        base: Decimal,
        amount: Decimal,
        note: str,
    ) -> CommissionEntry:
        return self._commissions.add(
            reseller_id=sale.seller_id,
            sale=sale,
            kind=kind.value,
            rate=rate,
            base_amount=base,
            amount=amount,
            note=note,
            available_at=self._available_at(sale),
        )

    # pending through the trial period after delivery (the sale date for a manual sale); later
    # entries of the sale (reversals, a rebased earning) keep the date of its first earning
    def _available_at(self, sale: Sale) -> datetime:
        if known := self._commissions.available_at(sale):
            return known
        delivery = self._books.delivery(sale.order_id) if self._books and sale.order_id else None
        start = delivery.delivered_at if delivery and delivery.delivered_at else sale.sold_at
        return start + timedelta(days=VALIDATION_DAYS)

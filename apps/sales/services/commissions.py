from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from apps.catalog.domain.enums import ProductOrigin
from apps.sales.domain.enums import CommissionKind, CommissionRule
from apps.sales.domain.payouts import VALIDATION_DAYS
from apps.sales.domain.rules import ZERO, CommissionLine, line_commission, proportional_reversal
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

    # decided once, when the sale is recorded or converted (kept on the sale as `commissionable`):
    # a reseller seller, not buying for themselves, and no points or coupon on the order
    def eligible(self, seller_id: int, buyer_id: int | None, *, real_money: bool = True) -> bool:
        if not real_money or seller_id == buyer_id:
            return False
        seller = self._sellers.profile(seller_id)
        return seller is not None and seller.role is Role.RESELLER

    def earn(self, sale: Sale) -> CommissionChange | None:
        if not sale.commissionable:
            return None
        commission = line_commission(
            CommissionLine(
                paid=sale.total,
                quantity=sale.quantity,
                unit_cost=sale.unit_cost,
                partner=sale.origin == ProductOrigin.PARTNER.value,
                partner_gain=sale.partner_gain,
            )
        )
        if commission.amount <= ZERO:
            return None
        self._entry(
            sale,
            kind=CommissionKind.EARNED,
            rule=commission.rule,
            base=sale.total,
            amount=commission.amount,
            note="Commission sur vente",
        )
        return CommissionChange(sale.seller_id, commission.amount)

    def reverse_refund(
        self, sale: Sale, refunded: Decimal, *, note: str
    ) -> CommissionChange | None:
        earned = self._commissions.last_earned(sale)
        net = self._commissions.net_for_sale(sale)
        if earned is None or net <= ZERO:
            return None
        amount = min(proportional_reversal(earned.amount, refunded, sale.total), net)
        if amount <= ZERO:
            return None
        self._entry(
            sale,
            kind=CommissionKind.REVERSED,
            rule=_rule(earned),
            base=refunded,
            amount=-amount,
            note=note,
        )
        return CommissionChange(sale.seller_id, -amount)

    def void(self, sale: Sale, *, note: str) -> CommissionChange | None:
        net = self._commissions.net_for_sale(sale)
        if net <= ZERO:
            return None
        self._entry(
            sale,
            kind=CommissionKind.REVERSED,
            rule=_rule(self._commissions.last_earned(sale)),
            base=sale.total,
            amount=-net,
            note=note,
        )
        return CommissionChange(sale.seller_id, -net)

    # a price edit: what was earned is voided and the commission is computed again on the new
    # price, with the origin, gain and cost the sale snapshotted
    def rebase(self, sale: Sale) -> list[CommissionChange]:
        if not sale.commissionable:
            return []
        changes = [change for change in [self.void(sale, note="Vente modifiée")] if change]
        if earned := self.earn(sale):
            changes.append(earned)
        return changes

    def _entry(
        self,
        sale: Sale,
        *,
        kind: CommissionKind,
        rule: CommissionRule,
        base: Decimal,
        amount: Decimal,
        note: str,
    ) -> CommissionEntry:
        return self._commissions.add(
            reseller_id=sale.seller_id,
            sale=sale,
            kind=kind.value,
            rule=rule.value,
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


def _rule(earned: CommissionEntry | None) -> CommissionRule:
    return CommissionRule(earned.rule) if earned is not None else CommissionRule.PAID

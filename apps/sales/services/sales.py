from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.orders.domain.enums import PaymentMethod
from apps.sales.domain.commands import ConvertOrder, EditSale, RecordSale, RefundSale
from apps.sales.domain.enums import RefundKind, SaleStatus
from apps.sales.domain.errors import (
    AlreadyReturned,
    InvalidSaleDate,
    InvalidSeller,
    OrderNotConvertible,
    RefundExceedsTotal,
    ReturnThroughOrder,
    SaleNotEditable,
    SellerRequired,
    UnknownOrderItems,
)
from apps.sales.domain.rules import ZERO, cents, refundable
from apps.sales.models import Sale
from apps.sales.repositories import SaleRepository
from apps.sales.services.commissions import CommissionChange, CommissionService
from apps.sales.services.contracts import Inventory, OrderBook, Sellers
from core.domain.actor import Actor, Role
from core.domain.values import provided

SALE_SOURCE = "sale"
BLOCKED_STATUSES = {"cancelled": "cancelled", "returned": "returned"}


@dataclass(slots=True)
class SaleOutcome:
    sales: list[Sale]
    commissions: list[CommissionChange] = field(default_factory=list)


class SaleService:
    def __init__(
        self,
        sales: SaleRepository,
        inventory: Inventory,
        commissions: CommissionService,
        sellers: Sellers,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._sales = sales
        self._inventory = inventory
        self._commissions = commissions
        self._sellers = sellers
        self._clock = clock

    def record(self, actor: Actor, command: RecordSale) -> SaleOutcome:
        seller_id = self._seller(actor, command.seller_id)
        sold_at = self._sold_at(command.sold_at)
        (line,) = self._inventory.price(
            [
                StockLine(
                    product_id=command.product_id,
                    variant_id=command.variant_id,
                    quantity=command.quantity,
                )
            ]
        )
        sale = self._sales.create(
            product_id=line.product_id,
            variant_id=line.variant_id,
            product_name=line.name,
            variant_label=line.variant_label,
            product_image=line.image,
            seller_id=seller_id,
            buyer_id=command.buyer_id,
            sold_to=" ".join(command.sold_to.split()),
            quantity=command.quantity,
            unit_price=command.unit_price,
            unit_cost=line.cost_price,
            payment_method=command.payment_method.value,
            recorded_by_id=actor.user_id,
            sold_at=sold_at,
        )
        self._inventory.reserve(
            [
                StockLine(
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    quantity=command.quantity,
                )
            ],
            StockSource(kind=SALE_SOURCE, id=sale.pk, actor_id=actor.user_id),
            reason=StockReason.SALE,
        )
        self._inventory.count_sales(line.product_id, command.quantity, actor_id=actor.user_id)
        earned = self._commissions.earn(sale)
        return SaleOutcome([sale], [earned] if earned else [])

    def convert(
        self, actor: Actor, books: OrderBook, order_id: int, command: ConvertOrder
    ) -> SaleOutcome:
        order = books.order(actor, order_id)
        if order.status.value in BLOCKED_STATUSES:
            raise OrderNotConvertible(BLOCKED_STATUSES[order.status.value])
        items = {item.id: item for item in order.items}
        if self._sales.converted_item_ids(items):
            raise OrderNotConvertible("already_converted")
        overrides = {line.item_id: line.unit_price for line in command.lines}
        if set(overrides) - set(items):
            raise UnknownOrderItems
        sold_at = self._sold_at(command.sold_at)
        seller_id = order.reseller_id or actor.user_id
        if seller_id is None:
            raise SellerRequired
        outcome = SaleOutcome([])
        for item in order.items:
            if item.product_id is None:
                continue
            cost = self._inventory.cost_of(item.product_id, item.variant_id)
            sale = self._sales.create(
                product_id=item.product_id,
                variant_id=item.variant_id,
                product_name=item.name,
                variant_label=item.variant_label,
                product_image=cost.image if cost else "",
                seller_id=seller_id,
                buyer_id=order.client_id,
                sold_to=" ".join(command.sold_to.split()) or order.client_name,
                quantity=item.quantity,
                unit_price=overrides.get(item.id, item.unit_price),
                unit_cost=cost.cost_price if cost else None,
                payment_method=(command.payment_method or order.payment_method).value,
                order_id=order.id,
                order_item_id=item.id,
                recorded_by_id=actor.user_id,
                sold_at=sold_at,
            )
            self._inventory.count_sales(item.product_id, item.quantity, actor_id=actor.user_id)
            outcome.sales.append(sale)
            if earned := self._commissions.earn(sale):
                outcome.commissions.append(earned)
        if not outcome.sales:
            raise OrderNotConvertible("no_products")
        if order.status.value != "delivered":
            books.mark_delivered(order.id, note="Commande convertie en ventes")
        return outcome

    def edit(self, sale: Sale, command: EditSale) -> SaleOutcome:
        if sale.sale_status is not SaleStatus.VALID:
            raise SaleNotEditable
        values = dict(provided(command))
        if "sold_at" in values:
            values["sold_at"] = self._sold_at(values["sold_at"])
        if "payment_method" in values:
            values["payment_method"] = PaymentMethod(values["payment_method"]).value
        if "sold_to" in values:
            values["sold_to"] = " ".join(values["sold_to"].split())
        price_changed = "unit_price" in values and values["unit_price"] != sale.unit_price
        for name, value in values.items():
            setattr(sale, name, value)
        if values:
            self._sales.save(sale, fields=values)
        return SaleOutcome([sale], self._commissions.rebase(sale) if price_changed else [])

    def refund(self, actor: Actor, sale: Sale, command: RefundSale) -> SaleOutcome:
        if sale.sale_status is SaleStatus.RETURNED:
            raise AlreadyReturned
        remaining = refundable(sale.total, sale.refunded_amount)
        if command.kind is RefundKind.RETURN:
            if sale.order_id is not None:
                raise ReturnThroughOrder
            amount = remaining
        else:
            amount = cents(command.amount or remaining)
        if amount <= ZERO or amount > remaining:
            raise RefundExceedsTotal(str(remaining))
        self._sales.add_refund(
            sale,
            kind=command.kind.value,
            amount=amount,
            reason=command.reason.strip(),
            by_id=actor.user_id,
        )
        sale.refunded_amount += amount
        sale.status = (
            SaleStatus.RETURNED.value
            if command.kind is RefundKind.RETURN
            else SaleStatus.REFUNDED.value
        )
        self._sales.save(sale, fields=("refunded_amount", "status"))
        if command.kind is RefundKind.RETURN:
            self._restock(actor, sale, StockReason.RETURN, "Retour de vente")
            self._inventory.count_sales(sale.product_id, -sale.quantity, actor_id=actor.user_id)
        reversal = self._commissions.reverse_refund(
            sale, amount, note="Retour" if command.kind is RefundKind.RETURN else "Remboursement"
        )
        return SaleOutcome([sale], [reversal] if reversal else [])

    def delete(self, actor: Actor, sale: Sale) -> SaleOutcome:
        changes = [
            change for change in [self._commissions.void(sale, note="Vente supprimée")] if change
        ]
        if sale.sale_status is not SaleStatus.RETURNED:
            if sale.order_id is None:
                self._restock(actor, sale, StockReason.CORRECTION, "Suppression de vente")
            self._inventory.count_sales(sale.product_id, -sale.quantity, actor_id=actor.user_id)
        self._sales.delete(sale)
        return SaleOutcome([], changes)

    def order_returned(self, actor: Actor, order_id: int) -> SaleOutcome:
        outcome = SaleOutcome([])
        for sale in self._sales.for_order(order_id, for_update=True):
            if sale.sale_status is SaleStatus.RETURNED:
                continue
            remaining = refundable(sale.total, sale.refunded_amount)
            if remaining > ZERO:
                self._sales.add_refund(
                    sale,
                    kind=RefundKind.RETURN.value,
                    amount=remaining,
                    reason="Commande retournée",
                    by_id=actor.user_id,
                )
            sale.refunded_amount = sale.total
            sale.status = SaleStatus.RETURNED.value
            self._sales.save(sale, fields=("refunded_amount", "status"))
            self._inventory.count_sales(sale.product_id, -sale.quantity, actor_id=actor.user_id)
            if reversal := self._commissions.void(sale, note="Commande retournée"):
                outcome.commissions.append(reversal)
            outcome.sales.append(sale)
        return outcome

    def _seller(self, actor: Actor, seller_id: int | None) -> int:
        if actor.role is Role.RESELLER or seller_id is None:
            if actor.user_id is None:
                raise SellerRequired
            return actor.user_id
        seller = self._sellers.profile(seller_id)
        if seller is None or not seller.role.includes(Role.RESELLER):
            raise InvalidSeller
        return seller.id

    def _sold_at(self, sold_at: datetime | None) -> datetime:
        now = self._clock()
        if sold_at is None:
            return now
        if sold_at > now:
            raise InvalidSaleDate
        return sold_at

    def _restock(self, actor: Actor, sale: Sale, reason: StockReason, note: str) -> None:
        self._inventory.release(
            [
                StockLine(
                    product_id=sale.product_id, variant_id=sale.variant_id, quantity=sale.quantity
                )
            ],
            StockSource(kind=SALE_SOURCE, id=sale.pk, actor_id=actor.user_id),
            reason=reason,
            note=note,
        )

from collections.abc import Sequence
from dataclasses import dataclass

from django.db import transaction

from apps.accounts.domain.read_models import SellerProfile
from apps.sales.domain.commands import (
    ConvertOrder,
    EditSale,
    RecordPayout,
    RecordSale,
    RefundSale,
    SaleFilters,
)
from apps.sales.domain.enums import RefundKind
from apps.sales.domain.errors import NotAReseller, SaleNotFound
from apps.sales.domain.events import (
    CommissionChanged,
    OrderConverted,
    PayoutRecorded,
    SaleDeleted,
    SaleRecorded,
    SaleRefunded,
    SaleUpdated,
)
from apps.sales.domain.read_models import (
    CommissionEntryView,
    CommissionSummary,
    ConvertibleOrderView,
    MonthlyCommission,
    PayoutView,
    PersonRef,
    SalesStats,
    SaleView,
)
from apps.sales.models import Sale
from apps.sales.selectors import (
    CommissionSelector,
    PayoutSelector,
    SaleSelector,
    scoped_sales,
    to_sale_view,
)
from apps.sales.services.commissions import CommissionChange
from apps.sales.services.contracts import OrderBook, Sellers
from apps.sales.services.payouts import PayoutService
from apps.sales.services.sales import SaleOutcome, SaleService
from core.domain.actor import Actor, Role
from core.domain.errors import DomainError, Forbidden, ValidationFailed
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@dataclass(frozen=True, slots=True)
class SalePage:
    sales: list[SaleView]
    total: int
    stats: SalesStats


@logged_facade
class SalesFacade:
    def __init__(
        self,
        *,
        sales: SaleService,
        selector: SaleSelector,
        books: OrderBook,
        publisher: EventPublisher,
    ) -> None:
        self._sales = sales
        self._selector = selector
        self._books = books
        self._publisher = publisher

    def page(self, actor: Actor, filters: SaleFilters, *, offset: int, limit: int) -> SalePage:
        return SalePage(*self._selector.page(actor, filters, offset=offset, limit=limit))

    def detail(self, actor: Actor, sale_id: int) -> SaleView:
        return self._selector.detail(actor, sale_id)

    def record(self, actor: Actor, command: RecordSale) -> SaleView:
        with transaction.atomic():
            outcome = self._sales.record(actor, command)
            self._recorded(actor, outcome)
        return self._selector.detail(actor, outcome.sales[0].pk)

    def record_many(self, actor: Actor, commands: Sequence[RecordSale]) -> list[SaleView]:
        with transaction.atomic():
            outcomes: list[SaleOutcome] = []
            for index, command in enumerate(commands, start=1):
                try:
                    outcomes.append(self._sales.record(actor, command))
                except DomainError as error:
                    raise ValidationFailed(
                        f"Ligne {index} : {error.detail}",
                        errors={"lines": [f"Ligne {index} : {error.detail}"]},
                        meta={"line": index, "code": error.code},
                    ) from error
            for outcome in outcomes:
                self._recorded(actor, outcome)
        return [to_sale_view(sale) for outcome in outcomes for sale in outcome.sales]

    def edit(self, actor: Actor, sale_id: int, command: EditSale) -> SaleView:
        with transaction.atomic():
            sale = self._locked(actor, sale_id)
            outcome = self._sales.edit(sale, command)
            self._publisher.publish(
                SaleUpdated(sale_id=sale.pk, seller_id=sale.seller_id, actor_id=actor.user_id)
            )
            self._commissions(actor, outcome.commissions)
        return self._selector.detail(actor, sale_id)

    def refund(self, actor: Actor, sale_id: int, command: RefundSale) -> SaleView:
        with transaction.atomic():
            sale = self._locked(actor, sale_id)
            before = sale.refunded_amount
            outcome = self._sales.refund(actor, sale, command)
            self._publisher.publish(
                SaleRefunded(
                    sale_id=sale.pk,
                    seller_id=sale.seller_id,
                    kind=command.kind,
                    amount=sale.refunded_amount - before,
                    actor_id=actor.user_id,
                )
            )
            self._commissions(actor, outcome.commissions)
        return self._selector.detail(actor, sale_id)

    def delete(self, actor: Actor, sale_id: int) -> None:
        with transaction.atomic():
            sale = self._locked(actor, sale_id)
            seller_id = sale.seller_id
            outcome = self._sales.delete(actor, sale)
            self._publisher.publish(
                SaleDeleted(sale_id=sale_id, seller_id=seller_id, actor_id=actor.user_id)
            )
            self._commissions(actor, outcome.commissions)

    def convertible(self, actor: Actor, search: str | None) -> list[ConvertibleOrderView]:
        orders = self._books.convertible(actor, search)
        converted = self._selector.converted_item_ids(
            item.id for order in orders for item in order.items
        )
        return [
            ConvertibleOrderView(
                id=order.id,
                number=order.number,
                status=order.status.value,
                client_name=order.client_name,
                total=order.total,
                created_at=order.created_at,
                convertible=not any(item.id in converted for item in order.items),
                blocked_reason="already_converted"
                if any(item.id in converted for item in order.items)
                else None,
                items_count=len(order.items),
            )
            for order in orders
        ]

    def convert(self, actor: Actor, order_id: int, command: ConvertOrder) -> list[SaleView]:
        with transaction.atomic():
            outcome = self._sales.convert(actor, self._books, order_id, command)
            self._recorded(actor, outcome)
            self._publisher.publish(
                OrderConverted(
                    order_id=order_id,
                    sale_ids=tuple(sale.pk for sale in outcome.sales),
                    actor_id=actor.user_id,
                )
            )
        return [self._selector.detail(actor, sale.pk) for sale in outcome.sales]

    def order_returned(self, order_id: int) -> None:
        actor = Actor.system()
        with transaction.atomic():
            outcome = self._sales.order_returned(actor, order_id)
            for sale in outcome.sales:
                self._publisher.publish(
                    SaleRefunded(
                        sale_id=sale.pk,
                        seller_id=sale.seller_id,
                        kind=RefundKind.RETURN,
                        amount=sale.total,
                    )
                )
            self._commissions(actor, outcome.commissions)

    def _locked(self, actor: Actor, sale_id: int) -> Sale:
        sale = scoped_sales(actor).select_for_update().filter(pk=sale_id).first()
        if sale is None:
            raise SaleNotFound
        return sale

    def _recorded(self, actor: Actor, outcome: SaleOutcome) -> None:
        for sale in outcome.sales:
            self._publisher.publish(
                SaleRecorded(
                    sale_id=sale.pk,
                    seller_id=sale.seller_id,
                    product_id=sale.product_id,
                    total=sale.total,
                    actor_id=actor.user_id,
                )
            )
        self._commissions(actor, outcome.commissions)

    def _commissions(self, actor: Actor, changes: Sequence[CommissionChange]) -> None:
        for change in changes:
            self._publisher.publish(
                CommissionChanged(
                    reseller_id=change.reseller_id, delta=change.delta, actor_id=actor.user_id
                )
            )


@logged_facade
class CommissionFacade:
    def __init__(
        self,
        *,
        payouts: PayoutService,
        selector: CommissionSelector,
        payout_selector: PayoutSelector,
        sellers: Sellers,
        publisher: EventPublisher,
    ) -> None:
        self._payouts = payouts
        self._selector = selector
        self._payout_selector = payout_selector
        self._sellers = sellers
        self._publisher = publisher

    def summary(self, actor: Actor, reseller_id: int | None) -> CommissionSummary:
        reseller = self._reseller(actor, reseller_id)
        return self._selector.summary(
            PersonRef(id=reseller.id, name=reseller.name), reseller.commission_rate
        )

    def overview(self) -> list[CommissionSummary]:
        return [
            self._selector.summary(
                PersonRef(id=reseller.id, name=reseller.name), reseller.commission_rate
            )
            for reseller in self._sellers.resellers()
        ]

    def entries(
        self, actor: Actor, reseller_id: int | None, *, offset: int, limit: int
    ) -> tuple[list[CommissionEntryView], int]:
        reseller = self._reseller(actor, reseller_id)
        return self._selector.entries(reseller.id, offset=offset, limit=limit)

    def monthly(self, actor: Actor, reseller_id: int | None) -> list[MonthlyCommission]:
        return self._selector.monthly(self._reseller(actor, reseller_id).id)

    def payouts(
        self, actor: Actor, reseller_id: int | None, *, offset: int, limit: int
    ) -> tuple[list[PayoutView], int]:
        scope = reseller_id if actor.is_staff else actor.user_id
        return self._payout_selector.page(scope, offset=offset, limit=limit)

    def record_payout(self, actor: Actor, command: RecordPayout) -> PayoutView:
        with transaction.atomic():
            payout = self._payouts.record(actor, command)
            self._publisher.publish(
                PayoutRecorded(
                    payout_id=payout.pk,
                    reseller_id=payout.reseller_id,
                    amount=payout.amount,
                    actor_id=actor.user_id,
                )
            )
        return self._payout_selector.one(payout.pk)

    def _reseller(self, actor: Actor, reseller_id: int | None) -> SellerProfile:
        if not actor.is_staff:
            reseller_id = actor.user_id
        elif reseller_id is None:
            raise ValidationFailed(errors={"reseller_id": ["Ce champ est obligatoire."]})
        profile = self._sellers.profile(reseller_id) if reseller_id is not None else None
        if profile is None or profile.role is not Role.RESELLER:
            if not actor.is_staff:
                raise Forbidden
            raise NotAReseller
        return profile

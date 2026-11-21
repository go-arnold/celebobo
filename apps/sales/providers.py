from django.utils import timezone

from apps.sales.adapters.gateways import AccountsSellers, CatalogInventory, OrdersBook
from apps.sales.facades import CommissionFacade, SalesFacade
from apps.sales.repositories import (
    CommissionRepository,
    DeliveryCreditRepository,
    PayoutRepository,
    SaleRepository,
    StatementRepository,
)
from apps.sales.selectors import (
    CommissionSelector,
    PayoutSelector,
    SaleSelector,
    StatementSelector,
)
from apps.sales.services.commissions import CommissionService
from apps.sales.services.contracts import Inventory, OrderBook, Sellers
from apps.sales.services.payouts import PayoutService
from apps.sales.services.sales import SaleService
from apps.sales.services.statements import DeliveryCreditService, StatementService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(Inventory, lambda _: CatalogInventory())
    container.register(OrderBook, lambda _: OrdersBook())
    container.register(Sellers, lambda _: AccountsSellers())
    container.register(SalesFacade, _sales_facade, lifetime=Lifetime.TRANSIENT)
    container.register(CommissionFacade, _commission_facade, lifetime=Lifetime.TRANSIENT)


def _commissions(container: Container) -> CommissionService:
    return CommissionService(
        CommissionRepository(), container.resolve(Sellers), books=container.resolve(OrderBook)
    )


def _statements() -> StatementService:
    return StatementService(StatementRepository(), clock=timezone.now)


def _sales_facade(container: Container) -> SalesFacade:
    return SalesFacade(
        sales=SaleService(
            SaleRepository(),
            container.resolve(Inventory),
            _commissions(container),
            container.resolve(Sellers),
            clock=timezone.now,
        ),
        selector=SaleSelector(),
        books=container.resolve(OrderBook),
        statements=_statements(),
        publisher=container.resolve(EventPublisher),
    )


def _commission_facade(container: Container) -> CommissionFacade:
    return CommissionFacade(
        payouts=PayoutService(PayoutRepository(), StatementRepository(), clock=timezone.now),
        statements=_statements(),
        delivery_credits=DeliveryCreditService(
            DeliveryCreditRepository(), container.resolve(OrderBook), container.resolve(Sellers)
        ),
        selector=CommissionSelector(),
        payout_selector=PayoutSelector(),
        statement_selector=StatementSelector(),
        sellers=container.resolve(Sellers),
        publisher=container.resolve(EventPublisher),
    )

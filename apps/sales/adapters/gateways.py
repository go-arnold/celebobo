from collections.abc import Sequence

from apps.accounts.domain.read_models import SellerProfile
from apps.accounts.selectors import SellerSelector
from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.catalog.facades import InventoryFacade
from apps.orders.domain.commands import TransitionOrder
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import ConvertibleOrder
from apps.orders.facades import DispatchFacade
from apps.orders.selectors import convertible_order, convertible_orders
from core.container import container
from core.domain.actor import Actor
from core.domain.errors import DomainError


class CatalogInventory:
    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]:
        return container.resolve(InventoryFacade).price(lines)

    def cost_of(self, product_id: int, variant_id: int | None) -> PricedLine | None:
        try:
            (line,) = self.price(
                [StockLine(product_id=product_id, variant_id=variant_id, quantity=1)]
            )
        except DomainError:
            return None
        return line

    def reserve(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason
    ) -> None:
        container.resolve(InventoryFacade).reserve(lines, source, reason=reason)

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None:
        container.resolve(InventoryFacade).release(lines, source, reason=reason, note=note)

    def count_sales(self, product_id: int, quantity: int, *, actor_id: int | None) -> None:
        container.resolve(InventoryFacade).record_sales(product_id, quantity, actor_id=actor_id)


class OrdersBook:
    def convertible(self, actor: Actor, search: str | None) -> list[ConvertibleOrder]:
        return convertible_orders(actor, search)

    def order(self, actor: Actor, order_id: int) -> ConvertibleOrder:
        return convertible_order(actor, order_id)

    def mark_delivered(self, order_id: int, *, note: str) -> None:
        container.resolve(DispatchFacade).transition(
            Actor.system(), order_id, TransitionOrder(to=OrderStatus.DELIVERED, note=note)
        )


class AccountsSellers:
    def profile(self, user_id: int) -> SellerProfile | None:
        return SellerSelector().profile(user_id)

    def resellers(self) -> list[SellerProfile]:
        return SellerSelector().resellers()

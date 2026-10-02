from collections.abc import Sequence

from apps.accounts.selectors import AddressSelector, ResellerSelector
from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.catalog.facades import InventoryFacade
from apps.orders.domain.commands import DeliveryAddress
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import PersonBrief
from apps.orders.models import Order, OrderItem
from core.container import container


class CatalogInventory:
    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]:
        return container.resolve(InventoryFacade).price(lines)

    def reserve(self, lines: Sequence[StockLine], source: StockSource) -> None:
        container.resolve(InventoryFacade).reserve(lines, source)

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> None:
        container.resolve(InventoryFacade).release(lines, source, reason=reason, note=note)


class AccountsAddressBook:
    def snapshot(self, user_id: int, address_id: int) -> DeliveryAddress:
        address = AddressSelector().one(user_id, address_id)
        return DeliveryAddress(
            recipient=address.recipient,
            phone=address.phone,
            line1=address.line1,
            quarter=address.quarter,
            city=address.city,
            country=address.country,
        )


class AccountsResellerDirectory:
    def active(self, reseller_id: int) -> PersonBrief | None:
        reseller = ResellerSelector().active(reseller_id)
        if reseller is None:
            return None
        return PersonBrief(
            id=reseller.id,
            name=reseller.name,
            email=reseller.email,
            availability=reseller.availability.value,
        )

    def assignable(self, search: str | None) -> list[PersonBrief]:
        return [
            PersonBrief(
                id=reseller.id,
                name=reseller.name,
                email=reseller.email,
                availability=reseller.availability.value,
            )
            for reseller in ResellerSelector().assignable(search)
        ]


class NoOrderThreads:
    def open_for_order(self, order: Order) -> int | None:
        return None

    def thread_for(self, order_id: int) -> int | None:
        return None


class DeliveredOrderPurchases:
    def has_received(self, user_id: int, product_id: int) -> bool:
        return OrderItem.objects.filter(
            order__client_id=user_id,
            order__status=OrderStatus.DELIVERED.value,
            product_id=product_id,
        ).exists()

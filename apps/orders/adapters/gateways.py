from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal

from django.db.models import Sum

from apps.accounts.selectors import AddressSelector, ReferralSelector, ResellerSelector
from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.catalog.facades import InventoryFacade
from apps.orders.domain.commands import DeliveryAddress
from apps.orders.domain.enums import OrderStatus
from apps.orders.domain.read_models import PersonBrief, SuggestedReseller
from apps.orders.models import Order, OrderItem
from core.container import container
from core.domain.actor import Actor


class CatalogInventory:
    def price(self, lines: Sequence[StockLine], *, lock: bool = False) -> list[PricedLine]:
        return container.resolve(InventoryFacade).price(lines, lock=lock)

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

    def default_city(self, user_id: int) -> str | None:
        addresses = AddressSelector().for_user(user_id)
        default = next((address for address in addresses if address.is_default), None)
        return default.city if default else None


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

    def inviters(self, client_ids: Iterable[int]) -> dict[int, SuggestedReseller]:
        return {
            client_id: SuggestedReseller(
                id=inviter.id, name=inviter.name, invited_at=inviter.invited_at
            )
            for client_id, inviter in ReferralSelector().inviting_resellers(client_ids).items()
        }


class NoWallet:
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return Decimal(0)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        return None

    def earned(self, order_id: int) -> Decimal | None:
        return None


class NoCreditWallet:
    def usable(self, user_id: int, base: Decimal, *, lock: bool = False) -> Decimal:
        return Decimal(0)

    def spend(self, user_id: int, order_id: int, amount: Decimal) -> None:
        return None


class NoCashGate:
    def blocked_reason(self, reseller_id: int) -> str | None:
        return None

    def blocked(self, reseller_ids: Iterable[int]) -> dict[int, str]:
        return {}


class NoSuspensions:
    def suspended_until(self, reseller_id: int) -> datetime | None:
        return None

    def suspended(self, reseller_ids: Iterable[int]) -> dict[int, datetime]:
        return {}


class NoOrderThreads:
    def open_for_order(self, order: Order) -> int | None:
        return None

    def thread_for(self, order_id: int, viewer: Actor | None = None) -> int | None:
        return None


class OrderDealSales:
    def sold(self, deal_ids: Sequence[int]) -> dict[int, int]:
        rows = (
            OrderItem.objects.filter(deal_id__in=deal_ids)
            .exclude(order__status=OrderStatus.CANCELLED.value)
            .values("deal_id")
            .annotate(units=Sum("quantity"))
        )
        return {row["deal_id"]: row["units"] for row in rows}


class DeliveredOrderPurchases:
    def has_received(self, user_id: int, product_id: int) -> bool:
        return OrderItem.objects.filter(
            order__client_id=user_id,
            order__status=OrderStatus.DELIVERED.value,
            product_id=product_id,
        ).exists()

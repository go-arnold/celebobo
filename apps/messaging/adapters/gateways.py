from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from apps.accounts.domain.enums import NotificationChannel, NotificationTopic
from apps.accounts.domain.read_models import Contact
from apps.accounts.selectors import DirectorySelector, ResellerSelector
from apps.messaging.repositories import (
    ConversationRepository,
    MessageRepository,
    NotificationRepository,
    ParticipantRepository,
)
from apps.messaging.selectors import visible_conversations
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.read_models import AdjustableItem, OrderRef, QuotableOrder
from apps.orders.facades import OrderAdjustmentFacade, OrderPrivacyFacade, ShippingQuoteFacade
from apps.orders.models import Order
from apps.orders.selectors import delivery_code, order_ref
from core.container import container
from core.domain.actor import Actor


class OrdersGateway:
    def ref(self, order_id: int) -> OrderRef:
        return order_ref(order_id)

    def adjustable(self, actor: Actor, order_id: int, item_id: int) -> AdjustableItem:
        return container.resolve(OrderAdjustmentFacade).adjustable(actor, order_id, item_id)

    def apply_price(
        self, actor: Actor, order_id: int, item_id: int, price: Decimal
    ) -> AdjustableItem:
        return container.resolve(OrderAdjustmentFacade).apply(actor, order_id, item_id, price)

    def delivery_code(self, order_id: int) -> str:
        return delivery_code(order_id)

    def shipping_quotable(self, actor: Actor, order_id: int) -> QuotableOrder:
        return container.resolve(ShippingQuoteFacade).quotable(actor, order_id)

    def accept_shipping(
        self, actor: Actor, order_id: int, fee: Decimal, delivery_estimate: str
    ) -> None:
        container.resolve(ShippingQuoteFacade).accept(actor, order_id, fee, delivery_estimate)

    def last_orders(self, client_ids: Iterable[int]) -> dict[int, datetime]:
        return container.resolve(OrderPrivacyFacade).last_orders(client_ids)


class AccountsDirectory:
    def staff_ids(self) -> list[int]:
        return DirectorySelector().staff_ids()

    def contacts(self, user_ids: Iterable[int]) -> dict[int, Contact]:
        return DirectorySelector().contacts(user_ids)

    def subscribed(self, user_ids: Iterable[int], topic: str, channel: str) -> set[int]:
        return DirectorySelector().subscribed(
            user_ids, NotificationTopic(topic), NotificationChannel(channel)
        )

    def reseller_name(self, reseller_id: int) -> str | None:
        reseller = ResellerSelector().active(reseller_id)
        return reseller.name if reseller else None


class MessagingOrderThreads:
    def open_for_order(self, order: Order) -> int | None:
        conversation = _conversations().open_for_order(
            order_id=order.pk, number=order.number, client_id=order.client_id
        )
        return conversation.pk

    def thread_for(self, order_id: int, viewer: Actor | None = None) -> int | None:
        if viewer is None:
            return ConversationRepository().id_for_order(order_id)
        threads = visible_conversations(viewer).filter(order_id=order_id)
        return threads.values_list("pk", flat=True).first()


def _conversations() -> ConversationService:
    return ConversationService(
        ConversationRepository(),
        MessageRepository(),
        ParticipantRepository(),
        NotificationRepository(),
        clock=timezone.now,
    )

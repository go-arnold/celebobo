from collections.abc import Iterable
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
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.read_models import AdjustableItem, OrderRef
from apps.orders.facades import OrderAdjustmentFacade
from apps.orders.models import Order
from apps.orders.selectors import order_ref
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

    def thread_for(self, order_id: int) -> int | None:
        return ConversationRepository().id_for_order(order_id)


def _conversations() -> ConversationService:
    return ConversationService(
        ConversationRepository(),
        MessageRepository(),
        ParticipantRepository(),
        NotificationRepository(),
        clock=timezone.now,
    )

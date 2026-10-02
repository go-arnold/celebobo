from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

from apps.messaging.domain.enums import NotificationKind
from apps.messaging.domain.notifications import RenderedNotification, preview, render
from apps.messaging.repositories import NotificationRepository
from apps.messaging.services.contracts import Delivery, Directory, Notifier, OrderGateway
from apps.orders.domain.enums import OrderStatus
from core.registry import Registry

notifier_registry: Registry[Notifier] = Registry("notification channel")


class NotificationService:
    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        self._notifiers = notifiers

    def notify(
        self,
        recipient_ids: Iterable[int],
        notification: RenderedNotification,
        *,
        conversation_id: int | None = None,
        order_id: int | None = None,
        exclude: Iterable[int | None] = (),
    ) -> None:
        skipped = {user_id for user_id in exclude if user_id is not None}
        recipients = tuple(sorted({pk for pk in recipient_ids if pk not in skipped}))
        if not recipients:
            return
        delivery = Delivery(
            recipient_ids=recipients,
            notification=notification,
            conversation_id=conversation_id,
            order_id=order_id,
        )
        for notifier in self._notifiers:
            notifier.deliver([delivery])


class InboxService:
    def __init__(
        self, notifications: NotificationRepository, *, clock: Callable[[], datetime]
    ) -> None:
        self._notifications = notifications
        self._clock = clock

    def mark_read(self, recipient_id: int, notification_id: int) -> bool:
        return self._notifications.mark_read(recipient_id, notification_id, self._clock())

    def mark_all_read(self, recipient_id: int) -> int:
        return self._notifications.mark_all_read(recipient_id, self._clock())


class NotificationFanout:
    def __init__(
        self,
        notifications: NotificationService,
        repository: NotificationRepository,
        orders: OrderGateway,
        directory: Directory,
    ) -> None:
        self._notifications = notifications
        self._repository = repository
        self._orders = orders
        self._directory = directory

    def order_placed(self, order_id: int) -> None:
        order = self._orders.ref(order_id)
        self._notifications.notify(
            self._directory.staff_ids(),
            render(
                NotificationKind.ORDER_PLACED,
                number=order.number,
                total=order.total,
                order_id=order.id,
            ),
            order_id=order.id,
        )

    def order_assigned(self, order_id: int, reseller_id: int) -> None:
        order = self._orders.ref(order_id)
        self._notifications.notify(
            [reseller_id],
            render(NotificationKind.ORDER_ASSIGNED, number=order.number, order_id=order.id),
            order_id=order.id,
        )

    def assignment_declined(self, order_id: int, reseller_id: int, reason: str) -> None:
        order = self._orders.ref(order_id)
        reseller = self._directory.contacts([reseller_id]).get(reseller_id)
        self._notifications.notify(
            self._directory.staff_ids(),
            render(
                NotificationKind.ASSIGNMENT_DECLINED,
                number=order.number,
                order_id=order.id,
                reseller=reseller.first_name if reseller else "Le revendeur",
                reason=reason,
            ),
            order_id=order.id,
        )

    def order_status_changed(
        self, order_id: int, status: OrderStatus, actor_id: int | None
    ) -> None:
        order = self._orders.ref(order_id)
        recipients = [order.client_id]
        if order.reseller_id is not None and status is not OrderStatus.ASSIGNED:
            recipients.append(order.reseller_id)
        self._notifications.notify(
            recipients,
            render(NotificationKind.ORDER_STATUS, number=order.number, status=status.label),
            order_id=order.id,
            exclude=[actor_id],
        )

    def message_posted(
        self,
        *,
        conversation_id: int,
        participant_ids: Iterable[int],
        sender_id: int,
        sender_name: str,
        body: str,
    ) -> None:
        recipients = [
            user_id
            for user_id in participant_ids
            if user_id != sender_id
            and not self._repository.unread_message_alert_exists(user_id, conversation_id)
        ]
        self._notifications.notify(
            recipients,
            render(
                NotificationKind.NEW_MESSAGE,
                sender=sender_name,
                preview=preview(body or "Pièce jointe"),
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
        )

    def support_opened(self, *, conversation_id: int, client_name: str, body: str) -> None:
        self._notifications.notify(
            self._directory.staff_ids(),
            render(
                NotificationKind.SUPPORT_REQUEST,
                client=client_name,
                preview=preview(body),
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
        )

    def conversation_assigned(
        self, *, conversation_id: int, reseller_id: int, client_name: str
    ) -> None:
        self._notifications.notify(
            [reseller_id],
            render(
                NotificationKind.CONVERSATION_ASSIGNED,
                client=client_name,
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
        )

    def price_proposed(
        self,
        *,
        conversation_id: int,
        client_id: int,
        product: str,
        old_price: str,
        new_price: str,
        reason: str,
    ) -> None:
        self._notifications.notify(
            [client_id],
            render(
                NotificationKind.PRICE_PROPOSED,
                product=product,
                old_price=old_price,
                new_price=new_price,
                reason=reason,
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
        )

    def price_answered(
        self,
        *,
        conversation_id: int,
        proposer_id: int | None,
        product: str,
        new_price: str,
        accepted: bool,
    ) -> None:
        if proposer_id is None:
            return
        self._notifications.notify(
            [proposer_id],
            render(
                NotificationKind.PRICE_ANSWERED,
                answer="acceptée" if accepted else "refusée",
                verb="accepté" if accepted else "refusé",
                product=product,
                new_price=new_price,
                conversation_id=conversation_id,
            ),
            conversation_id=conversation_id,
        )

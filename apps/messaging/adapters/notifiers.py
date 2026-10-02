from collections.abc import Sequence

from django.conf import settings

from apps.messaging.domain.events import NotificationCreated
from apps.messaging.models import Notification
from apps.messaging.repositories import NotificationRepository
from apps.messaging.services.contracts import Delivery, Directory
from apps.messaging.services.notifications import notifier_registry
from apps.push.domain.messages import PushMessage
from apps.push.facades import PushFacade
from core.container import container
from core.events.contracts import EventPublisher
from core.mail import queue_templated

EMAIL_CHANNEL = "email"
PUSH_CHANNEL = "push"
EMAIL_TEMPLATE = "messaging/email/notification"


@notifier_registry.register("in_app")
class InAppNotifier:
    def __init__(self, repository: NotificationRepository | None = None) -> None:
        self._repository = repository or NotificationRepository()

    def deliver(self, deliveries: Sequence[Delivery]) -> None:
        created = self._repository.create_many(
            Notification(
                recipient_id=recipient_id,
                kind=delivery.notification.kind.value,
                title=delivery.notification.title[:200],
                body=delivery.notification.body[:500],
                link=delivery.notification.link,
                conversation_id=delivery.conversation_id,
                order_id=delivery.order_id,
            )
            for delivery in deliveries
            for recipient_id in delivery.recipient_ids
        )
        publisher = container.resolve(EventPublisher)
        for notification in created:
            publisher.publish(
                NotificationCreated(
                    notification_id=notification.pk, recipient_id=notification.recipient_id
                )
            )


@notifier_registry.register("email")
class EmailNotifier:
    def deliver(self, deliveries: Sequence[Delivery]) -> None:
        directory = container.resolve(Directory)
        base_url = str(settings.FRONTEND_URL).rstrip("/")
        for delivery in deliveries:
            notification = delivery.notification
            subscribed = directory.subscribed(
                delivery.recipient_ids, notification.topic, EMAIL_CHANNEL
            )
            contacts = directory.contacts(subscribed)
            for contact in contacts.values():
                queue_templated(
                    EMAIL_TEMPLATE,
                    to=[contact.email],
                    subject=f"Celebobo — {notification.title}",
                    context={
                        "first_name": contact.first_name,
                        "title": notification.title,
                        "body": notification.body,
                        "url": f"{base_url}{notification.link}",
                    },
                )


@notifier_registry.register("push")
class PushNotifier:
    def deliver(self, deliveries: Sequence[Delivery]) -> None:
        directory = container.resolve(Directory)
        push = container.resolve(PushFacade)
        base_url = str(settings.FRONTEND_URL).rstrip("/")
        for delivery in deliveries:
            notification = delivery.notification
            recipients = directory.subscribed(
                delivery.recipient_ids, notification.topic, PUSH_CHANNEL
            )
            if recipients:
                push.send(
                    recipients,
                    PushMessage(
                        title=notification.title,
                        body=notification.body,
                        url=f"{base_url}{notification.link}",
                        tag=notification.kind.value,
                    ),
                )

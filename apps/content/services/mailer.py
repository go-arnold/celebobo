from django.conf import settings

from apps.content.models import ContactMessage, SiteSettings, Subscriber
from core.mail import queue_templated

UNSUBSCRIBE_PATH = "/newsletter/desinscription?token={token}"


class ContentMailer:
    def contact_received(self, message: ContactMessage, site: SiteSettings) -> None:
        queue_templated(
            "content/email/contact_ack",
            to=[message.email],
            subject="Celebobo — Nous avons bien reçu votre message",
            context={"name": message.name, "subject": message.get_subject_display()},
        )
        if site.email:
            queue_templated(
                "content/email/contact_alert",
                to=[site.email],
                subject=f"Celebobo — Nouveau message : {message.get_subject_display()}",
                context={"message": message},
            )

    def welcome(self, subscriber: Subscriber, site: SiteSettings) -> None:
        base = str(settings.FRONTEND_URL).rstrip("/")
        queue_templated(
            "content/email/newsletter_welcome",
            to=[subscriber.email],
            subject="Celebobo — Bienvenue dans la newsletter",
            context={
                "code": site.newsletter_code,
                "discount": site.newsletter_discount,
                "unsubscribe_url": base + UNSUBSCRIBE_PATH.format(token=subscriber.token),
            },
        )

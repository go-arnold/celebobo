from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template.loader import render_to_string


def queue_message(message: EmailMessage) -> None:
    deliver_email.delay(serialize_message(message))


def queue_templated(
    template_prefix: str, *, to: list[str], context: dict[str, Any], subject: str
) -> None:
    body = render_to_string(f"{template_prefix}_message.txt", context).strip()
    message = EmailMultiAlternatives(
        subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=to
    )
    queue_message(message)


def serialize_message(message: EmailMessage) -> dict[str, Any]:
    alternatives = getattr(message, "alternatives", [])
    return {
        "subject": str(message.subject),
        "body": str(message.body),
        "from_email": message.from_email,
        "to": list(message.to),
        "cc": list(message.cc),
        "bcc": list(message.bcc),
        "reply_to": list(message.reply_to),
        "headers": dict(message.extra_headers),
        "alternatives": [[content, mimetype] for content, mimetype in alternatives],
    }


def build_message(payload: dict[str, Any]) -> EmailMultiAlternatives:
    message = EmailMultiAlternatives(
        subject=payload["subject"],
        body=payload["body"],
        from_email=payload["from_email"],
        to=payload["to"],
        cc=payload["cc"],
        bcc=payload["bcc"],
        reply_to=payload["reply_to"],
        headers=payload["headers"],
    )
    for content, mimetype in payload["alternatives"]:
        message.attach_alternative(content, mimetype)
    return message


@shared_task(
    name="core.mail.deliver",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=6,
    acks_late=True,
)
def deliver_email(payload: dict[str, Any]) -> None:
    build_message(payload).send(fail_silently=False)

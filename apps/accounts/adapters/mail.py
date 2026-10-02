from typing import Any

from django.core.mail import EmailMessage, EmailMultiAlternatives


def serialize_message(message: EmailMessage) -> dict[str, Any]:
    alternatives = getattr(message, "alternatives", [])
    return {
        "subject": message.subject,
        "body": message.body,
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


def queue_message(message: EmailMessage) -> None:
    from apps.accounts.tasks import deliver_email

    deliver_email.delay(serialize_message(message))

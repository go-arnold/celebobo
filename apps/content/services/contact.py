from collections.abc import Callable
from datetime import datetime

from apps.accounts.domain.normalization import clean_text, normalize_email
from apps.content.domain.commands import HandleContactMessage, SendContactMessage
from apps.content.domain.enums import ContactStatus
from apps.content.domain.errors import ContactMessageNotFound
from apps.content.models import ContactMessage
from apps.content.repositories import ModelRepository
from apps.content.services.editors import Editor
from core.domain.actor import Actor
from core.domain.values import provided


class ContactService:
    def __init__(
        self, messages: ModelRepository[ContactMessage], *, clock: Callable[[], datetime]
    ) -> None:
        self._messages = messages
        self._editor = Editor(messages, not_found=ContactMessageNotFound)
        self._clock = clock

    def submit(self, actor: Actor, command: SendContactMessage, *, spam: bool) -> ContactMessage:
        return self._messages.create(
            name=clean_text(command.name),
            email=normalize_email(command.email),
            phone=clean_text(command.phone),
            subject=command.subject.value,
            message=command.message.strip(),
            user_id=actor.user_id,
            status=(ContactStatus.SPAM if spam else ContactStatus.NEW).value,
        )

    def get(self, message_id: int) -> ContactMessage:
        return self._editor.get(message_id)

    def handle(
        self, actor: Actor, message_id: int, command: HandleContactMessage
    ) -> ContactMessage:
        message = self._editor.get(message_id, for_update=True)
        values = dict(provided(command))
        fields = []
        if "note" in values:
            message.note = values["note"].strip()
            fields.append("note")
        status = values.get("status")
        if status is not None and status.value != message.status:
            message.status = status.value
            message.handled_by_id = actor.user_id if status is ContactStatus.HANDLED else None
            message.handled_at = self._clock() if status is ContactStatus.HANDLED else None
            fields += ["status", "handled_by", "handled_at"]
        if fields:
            self._messages.save(message, fields=fields)
        return message

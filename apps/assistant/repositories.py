from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from django.db.models import F

from apps.assistant.models import AssistantMessage, AssistantSession, ProductEmbedding


class EmbeddingRepository:
    def hashes(self, product_ids: Iterable[int]) -> dict[int, str]:
        return dict(
            ProductEmbedding.objects.filter(product_id__in=list(product_ids)).values_list(
                "product_id", "content_hash"
            )
        )

    def upsert(self, product_id: int, **fields: Any) -> None:
        ProductEmbedding.objects.update_or_create(product_id=product_id, defaults=fields)

    def update_metadata(self, product_id: int, **fields: Any) -> None:
        ProductEmbedding.objects.filter(product_id=product_id).update(**fields)

    def delete(self, product_ids: Iterable[int]) -> int:
        deleted, _ = ProductEmbedding.objects.filter(product_id__in=list(product_ids)).delete()
        return deleted


class SessionRepository:
    def create(self, *, user_id: int | None, title: str = "") -> AssistantSession:
        return AssistantSession.objects.create(user_id=user_id, title=title)

    def get(self, session_id: UUID, *, for_update: bool = False) -> AssistantSession | None:
        queryset = (
            AssistantSession.objects.select_for_update()
            if for_update
            else AssistantSession.objects.all()
        )
        return queryset.filter(pk=session_id).first()

    def save(self, session: AssistantSession, *, fields: Iterable[str]) -> None:
        session.save(update_fields=[*fields, "updated_at"])

    def count_message(self, session: AssistantSession, *, title: str) -> None:
        AssistantSession.objects.filter(pk=session.pk).update(message_count=F("message_count") + 1)
        if title and not session.title:
            AssistantSession.objects.filter(pk=session.pk, title="").update(title=title)
        session.refresh_from_db(fields=("message_count", "title", "updated_at"))

    def delete(self, session: AssistantSession) -> None:
        session.delete()


class MessageRepository:
    def add(self, session: AssistantSession, **fields: Any) -> AssistantMessage:
        return AssistantMessage.objects.create(session=session, **fields)

    def get(self, message_id: int) -> AssistantMessage | None:
        return AssistantMessage.objects.filter(pk=message_id).first()

    def save(self, message: AssistantMessage, *, fields: Sequence[str]) -> None:
        message.save(update_fields=list(fields))

    def recent(self, session_id: UUID, *, limit: int) -> list[AssistantMessage]:
        messages = AssistantMessage.objects.filter(session_id=session_id).exclude(content="")
        return list(reversed(messages.order_by("-created_at", "-pk")[:limit]))

    def window(self, session_id: UUID, *, start: int, stop: int) -> list[AssistantMessage]:
        messages = AssistantMessage.objects.filter(session_id=session_id).order_by(
            "created_at", "pk"
        )
        return list(messages[start:stop])

    def answered_today(self, today: date) -> int:
        return AssistantMessage.objects.filter(role="assistant", created_at__date=today).count()

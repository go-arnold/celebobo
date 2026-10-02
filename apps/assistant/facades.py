from collections.abc import AsyncIterator
from uuid import UUID

from django.db import transaction

from apps.assistant.domain.conversation import StreamEvent
from apps.assistant.domain.events import EmbeddingsReindexRequested
from apps.assistant.domain.queries import LogFilters
from apps.assistant.domain.read_models import (
    AssistantStats,
    QuestionLog,
    SessionDetail,
    SessionView,
)
from apps.assistant.selectors import LogSelector, SessionSelector, to_session_view
from apps.assistant.services.chat import ChatService, PendingTurn
from apps.assistant.services.conversations import ConversationStore
from apps.assistant.services.embeddings import EmbeddingService
from apps.assistant.services.followups import InsightService, MemoryService
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@logged_facade
class AssistantFacade:
    def __init__(
        self, *, store: ConversationStore, chat: ChatService, sessions: SessionSelector
    ) -> None:
        self._store = store
        self._chat = chat
        self._sessions = sessions

    def open(self, actor: Actor) -> SessionView:
        return to_session_view(self._store.open(actor))

    def sessions(self, actor: Actor, *, offset: int, limit: int) -> tuple[list[SessionView], int]:
        if actor.user_id is None:
            raise Unauthenticated
        return self._sessions.page(actor.user_id, offset=offset, limit=limit)

    def detail(self, actor: Actor, session_id: UUID) -> SessionDetail:
        return self._sessions.detail(self._store.owned(actor, session_id))

    def close(self, actor: Actor, session_id: UUID) -> None:
        with transaction.atomic():
            self._store.close(actor, session_id)

    def ask(self, actor: Actor, session_id: UUID, text: str) -> PendingTurn:
        return self._chat.ask(actor, session_id, text)

    def reply(self, actor: Actor, pending: PendingTurn) -> AsyncIterator[StreamEvent]:
        return self._chat.reply(actor, pending)


@logged_facade
class AssistantInsightsFacade:
    def __init__(
        self,
        *,
        logs: LogSelector,
        insights: InsightService,
        memory: MemoryService,
        embeddings: EmbeddingService,
        publisher: EventPublisher,
    ) -> None:
        self._logs = logs
        self._insights = insights
        self._memory = memory
        self._embeddings = embeddings
        self._publisher = publisher

    def logs(
        self, filters: LogFilters, *, offset: int, limit: int
    ) -> tuple[list[QuestionLog], int]:
        return self._logs.page(filters, offset=offset, limit=limit)

    def stats(self, filters: LogFilters) -> AssistantStats:
        return self._logs.stats(filters)

    def follow_up(self, session_id: UUID, question_id: int) -> None:
        with transaction.atomic():
            self._insights.analyze(question_id)
            self._memory.refresh(session_id)

    def refresh_embeddings(self, product_ids: list[int]) -> dict[str, int]:
        with transaction.atomic():
            return self._embeddings.refresh(product_ids)

    def request_reindex(self, actor: Actor) -> None:
        with transaction.atomic():
            self._publisher.publish(EmbeddingsReindexRequested(actor_id=actor.user_id))

    def reindex(self) -> dict[str, int]:
        return self._embeddings.reindex()

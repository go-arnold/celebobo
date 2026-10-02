from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction

from apps.assistant.domain.conversation import ChatMessage, Usage
from apps.assistant.domain.enums import Role
from apps.assistant.domain.errors import AssistantQuotaExceeded, QuestionTooLong, SessionNotFound
from apps.assistant.domain.events import AssistantReplied
from apps.assistant.domain.prompts import MEMORY_PROMPT, SYSTEM_PROMPT
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.assistant.repositories import MessageRepository, SessionRepository
from core.domain.actor import Actor
from core.events.contracts import EventPublisher

TITLE_LENGTH = 60


class ConversationStore:
    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        publisher: EventPublisher,
        *,
        memory_messages: int,
        max_question_length: int,
        daily_messages: int,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._publisher = publisher
        self._memory_messages = memory_messages
        self._max_question_length = max_question_length
        self._daily_messages = daily_messages
        self._clock = clock

    def open(self, actor: Actor) -> AssistantSession:
        return self._sessions.create(user_id=actor.user_id)

    def owned(self, actor: Actor, session_id: UUID) -> AssistantSession:
        session = self._sessions.get(session_id)
        if session is None or (session.user_id is not None and session.user_id != actor.user_id):
            raise SessionNotFound
        return session

    def close(self, actor: Actor, session_id: UUID) -> None:
        self._sessions.delete(self.owned(actor, session_id))

    def accept(
        self, actor: Actor, session_id: UUID, text: str
    ) -> tuple[AssistantSession, AssistantMessage]:
        question = text.strip()
        if len(question) > self._max_question_length:
            raise QuestionTooLong(self._max_question_length)
        if self._messages.answered_today(self._clock().date()) >= self._daily_messages:
            raise AssistantQuotaExceeded
        with transaction.atomic():
            session = self.owned(actor, session_id)
            message = self._messages.add(session, role=Role.USER.value, content=question)
            self._sessions.count_message(session, title=question[:TITLE_LENGTH])
        return session, message

    def prompt(self, session: AssistantSession) -> tuple[str, list[ChatMessage]]:
        system = SYSTEM_PROMPT
        if session.summary:
            system = f"{system}\n\n{MEMORY_PROMPT.format(summary=session.summary)}"
        history = self._messages.recent(session.pk, limit=self._memory_messages)
        return system, [ChatMessage(Role(message.role), message.content) for message in history]

    def finish(
        self,
        actor: Actor,
        session: AssistantSession,
        question: AssistantMessage,
        *,
        answer: str,
        product_ids: Sequence[int],
        tool_calls: list[dict[str, Any]],
        usage: Usage,
        cost: Any,
        latency_ms: int,
        error_code: str = "",
    ) -> AssistantMessage:
        with transaction.atomic():
            reply = self._messages.add(
                session,
                role=Role.ASSISTANT.value,
                content=answer,
                product_ids=list(product_ids),
                tool_calls=tool_calls,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost=cost,
                latency_ms=latency_ms,
                error_code=error_code,
            )
            if answer and not error_code:
                self._sessions.count_message(session, title="")
            self._publisher.publish(
                AssistantReplied(
                    session_id=session.pk,
                    question_id=question.pk,
                    answer_id=reply.pk,
                    actor_id=actor.user_id,
                )
            )
        return reply

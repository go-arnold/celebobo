import json
from uuid import UUID

from apps.assistant.domain.enums import Role, Sentiment
from apps.assistant.domain.prompts import INSIGHT_PROMPT, SUMMARY_PROMPT, SYSTEM_PROMPT
from apps.assistant.repositories import MessageRepository, SessionRepository
from apps.assistant.services.contracts import ChatModel

TOPIC_LENGTH = 60


class InsightService:
    def __init__(self, messages: MessageRepository, model: ChatModel) -> None:
        self._messages = messages
        self._model = model

    def analyze(self, question_id: int) -> bool:
        question = self._messages.get(question_id)
        if question is None or question.role != Role.USER.value or question.sentiment:
            return False
        raw = self._model.complete(
            system="", prompt=INSIGHT_PROMPT.format(question=question.content)
        )
        sentiment, topic = parse_insight(raw)
        question.sentiment = sentiment.value
        question.topic = topic
        self._messages.save(question, fields=("sentiment", "topic"))
        return True


class MemoryService:
    def __init__(
        self,
        sessions: SessionRepository,
        messages: MessageRepository,
        model: ChatModel,
        *,
        memory_messages: int,
        summary_every: int,
    ) -> None:
        self._sessions = sessions
        self._messages = messages
        self._model = model
        self._memory_messages = memory_messages
        self._summary_every = summary_every

    def refresh(self, session_id: UUID) -> bool:
        session = self._sessions.get(session_id, for_update=True)
        if session is None:
            return False
        upto = session.message_count - self._memory_messages
        if upto - session.summarized_count < self._summary_every:
            return False
        exchanges = self._messages.window(session.pk, start=session.summarized_count, stop=upto)
        lines = "\n".join(
            f"{'Client' if message.role == Role.USER.value else 'Assistant'} : {message.content}"
            for message in exchanges
            if message.content
        )
        session.summary = self._model.complete(
            system=SYSTEM_PROMPT,
            prompt=SUMMARY_PROMPT.format(summary=session.summary or "—", exchanges=lines),
        ).strip()
        session.summarized_count = upto
        self._sessions.save(session, fields=("summary", "summarized_count"))
        return True


def parse_insight(raw: str) -> tuple[Sentiment, str]:
    start, end = raw.find("{"), raw.rfind("}")
    try:
        data = json.loads(raw[start : end + 1]) if start != -1 and end > start else {}
    except json.JSONDecodeError:
        data = {}
    try:
        sentiment = Sentiment(str(data.get("sentiment", "")).lower())
    except ValueError:
        sentiment = Sentiment.NEUTRAL
    topic = str(data.get("topic") or "").strip().lower()[:TOPIC_LENGTH]
    return sentiment, topic

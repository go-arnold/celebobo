from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.assistant.domain.enums import Role, Sentiment


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageView:
    id: int
    role: Role
    content: str
    product_ids: tuple[int, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionView:
    id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionDetail:
    session: SessionView
    messages: list[MessageView]


@dataclass(frozen=True, slots=True, kw_only=True)
class QuestionLog:
    id: int
    session_id: UUID
    user_id: int | None
    question: str
    answer: str
    sentiment: Sentiment | None
    topic: str
    products_count: int
    input_tokens: int
    output_tokens: int
    cost: Decimal
    latency_ms: int
    error_code: str
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class AssistantStats:
    questions: int
    sessions: int
    input_tokens: int
    output_tokens: int
    cost: Decimal
    average_latency_ms: int
    sentiments: dict[str, int]
    top_topics: list[tuple[str, int]]

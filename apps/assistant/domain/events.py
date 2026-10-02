from uuid import UUID

from core.events.base import DomainEvent, domain_event


@domain_event
class AssistantReplied(DomainEvent):
    session_id: UUID
    question_id: int
    answer_id: int


@domain_event
class EmbeddingsReindexRequested(DomainEvent):
    pass

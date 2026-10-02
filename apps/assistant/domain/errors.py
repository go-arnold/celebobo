from core.domain.errors import NotFound, ServiceUnavailable, ValidationFailed


class SessionNotFound(NotFound):
    default_code = "assistant_session_not_found"
    default_detail = "Conversation introuvable."


class QuestionTooLong(ValidationFailed):
    default_code = "question_too_long"
    default_detail = "La question est trop longue."

    def __init__(self, limit: int) -> None:
        super().__init__(errors={"content": [f"{limit} caractères maximum."]})


class AssistantQuotaExceeded(ServiceUnavailable):
    default_code = "assistant_quota_exceeded"
    default_detail = "L'assistant a atteint sa limite du jour. Réessayez demain."


class AssistantUnavailable(ServiceUnavailable):
    default_code = "assistant_unavailable"
    default_detail = "L'assistant est momentanément indisponible."

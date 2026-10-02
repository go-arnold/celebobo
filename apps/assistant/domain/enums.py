from enum import StrEnum


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class EmbeddingTask(StrEnum):
    DOCUMENT = "document"
    QUERY = "query"

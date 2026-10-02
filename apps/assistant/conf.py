from dataclasses import dataclass
from decimal import Decimal

from core.conf import load_section

EMBEDDING_DIMENSIONS = 768


@dataclass(frozen=True, slots=True)
class AssistantSettings:
    provider: str = "offline"
    api_key: str = ""
    chat_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    memory_messages: int = 8
    summary_every: int = 6
    max_question_length: int = 1000
    search_limit: int = 6
    daily_messages: int = 2000
    input_cost_per_million: str = "0.30"
    output_cost_per_million: str = "2.50"
    max_tool_rounds: int = 2

    @property
    def input_cost(self) -> Decimal:
        return Decimal(self.input_cost_per_million)

    @property
    def output_cost(self) -> Decimal:
        return Decimal(self.output_cost_per_million)


def assistant_settings() -> AssistantSettings:
    return load_section("ASSISTANT", AssistantSettings)

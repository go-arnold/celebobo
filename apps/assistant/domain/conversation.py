from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.assistant.domain.enums import Role


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    text: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def cost(self, *, input_price: Decimal, output_price: Decimal) -> Decimal:
        million = Decimal(1_000_000)
        total = (
            self.input_tokens * input_price / million + self.output_tokens * output_price / million
        )
        return total.quantize(Decimal("0.000001"))


type ChatEvent = TextDelta | ToolInvocation | Usage
type ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class StreamEvent:
    name: str
    data: dict[str, Any] = field(default_factory=dict)

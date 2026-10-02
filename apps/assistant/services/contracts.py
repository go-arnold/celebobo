from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from apps.assistant.domain.conversation import ChatEvent, ChatMessage, ToolExecutor, ToolSpec
from apps.assistant.domain.enums import EmbeddingTask
from apps.catalog.domain.read_models import ProductCard
from core.domain.actor import Actor


class ChatModel(Protocol):
    name: str

    def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        execute: ToolExecutor,
    ) -> AsyncIterator[ChatEvent]: ...

    def complete(self, *, system: str, prompt: str) -> str: ...


class Embedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str], *, task: EmbeddingTask) -> list[list[float]]: ...


class ProductDocuments(Protocol):
    def documents(self, ids: Sequence[int]) -> list[dict[str, Any]]: ...

    def all_ids(self) -> list[int]: ...


class ProductCards(Protocol):
    def cards(self, actor: Actor, ids: Sequence[int]) -> list[ProductCard]: ...

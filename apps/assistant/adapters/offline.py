import hashlib
import json
import math
import re
import unicodedata
from collections.abc import AsyncIterator, Sequence
from typing import Any

from apps.assistant.conf import EMBEDDING_DIMENSIONS
from apps.assistant.domain.conversation import (
    ChatEvent,
    ChatMessage,
    TextDelta,
    ToolExecutor,
    ToolInvocation,
    ToolSpec,
    Usage,
)
from apps.assistant.domain.enums import EmbeddingTask

TOKEN = re.compile(r"[a-z0-9]+")
NEGATIVE_WORDS = frozenset(
    {"probleme", "panne", "retard", "nul", "decu", "arnaque", "casse", "lent"}
)
POSITIVE_WORDS = frozenset({"merci", "super", "parfait", "genial", "top", "excellent"})
TOPICS = {
    "livraison": "livraison",
    "prix": "prix",
    "promo": "promotion",
    "paiement": "paiement",
    "retour": "retour",
    "telephone": "smartphone",
    "smartphone": "smartphone",
    "chargeur": "accessoire",
    "coque": "accessoire",
}


def tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return TOKEN.findall(plain)


class HashingEmbedder:
    name = "offline-hashing"

    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        self._dimensions = dimensions

    def embed(self, texts: Sequence[str], *, task: EmbeddingTask) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in tokens(text):
            for feature in (token, token[:5]):
                digest = int(hashlib.blake2b(feature.encode(), digest_size=8).hexdigest(), 16)
                vector[digest % self._dimensions] += 1.0 if digest & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class OfflineChatModel:
    name = "offline"

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        execute: ToolExecutor,
    ) -> AsyncIterator[ChatEvent]:
        question = messages[-1].text if messages else ""
        products: list[dict[str, Any]] = []
        if tools:
            arguments = {"query": question}
            result = await execute(tools[0].name, arguments)
            products = list(result.get("products", []))
            yield ToolInvocation(tools[0].name, arguments, result)
        answer = _answer(products)
        for word in answer.split(" "):
            yield TextDelta(f"{word} ")
        yield Usage(input_tokens=len(tokens(system + question)), output_tokens=len(tokens(answer)))

    def complete(self, *, system: str, prompt: str) -> str:
        if "JSON" in prompt:
            question = prompt.rsplit("Question :", 1)[-1]
            return json.dumps(_insight(question))
        return " ".join(prompt.split()[-80:])


def _answer(products: list[dict[str, Any]]) -> str:
    if not products:
        return "Je n'ai pas trouvé de produit correspondant. Pouvez-vous préciser votre besoin ?"
    lines = ", ".join(f"{item['name']} à {item['price']} $" for item in products[:3])
    return f"Voici ce que je vous propose : {lines}."


def _insight(question: str) -> dict[str, str]:
    words = set(tokens(question))
    sentiment = "neutral"
    if words & NEGATIVE_WORDS:
        sentiment = "negative"
    elif words & POSITIVE_WORDS:
        sentiment = "positive"
    topic = next((label for word, label in TOPICS.items() if word in words), "autre")
    return {"sentiment": sentiment, "topic": topic}

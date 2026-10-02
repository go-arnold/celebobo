from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from decimal import Decimal
from time import monotonic
from typing import Any
from uuid import UUID

from asgiref.sync import sync_to_async

from apps.assistant.domain.conversation import (
    StreamEvent,
    TextDelta,
    ToolInvocation,
    ToolSpec,
    Usage,
)
from apps.assistant.domain.prompts import (
    SEARCH_TOOL_DESCRIPTION,
    SEARCH_TOOL_NAME,
    SEARCH_TOOL_PARAMETERS,
)
from apps.assistant.domain.queries import ProductQuery
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.assistant.services.contracts import ChatModel
from apps.assistant.services.conversations import ConversationStore
from apps.assistant.services.search import ProductSearch, tool_result
from core.domain.actor import Actor
from core.domain.errors import DomainError

SEARCH_TOOL = ToolSpec(SEARCH_TOOL_NAME, SEARCH_TOOL_DESCRIPTION, SEARCH_TOOL_PARAMETERS)


class ChatService:
    def __init__(
        self,
        store: ConversationStore,
        model: ChatModel,
        search: ProductSearch,
        *,
        input_price: Decimal,
        output_price: Decimal,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._store = store
        self._model = model
        self._search = search
        self._input_price = input_price
        self._output_price = output_price
        self._clock = clock

    def ask(self, actor: Actor, session_id: UUID, text: str) -> "PendingTurn":
        session, question = self._store.accept(actor, session_id, text)
        return PendingTurn(session=session, question=question)

    async def reply(self, actor: Actor, pending: "PendingTurn") -> AsyncIterator[StreamEvent]:
        session, question, text = pending.session, pending.question, pending.question.content
        system, history = await sync_to_async(self._store.prompt)(session)
        turn = _Turn()
        started = self._clock()

        async def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            turn.calls.append({"name": name, "arguments": arguments})
            if name != SEARCH_TOOL_NAME:
                return {"error": f"Outil inconnu : {name}"}
            ids = await sync_to_async(self._search.search)(_query(arguments, fallback=text))
            cards = await sync_to_async(self._search.cards)(actor, ids)
            turn.found.extend(card.id for card in cards if card.id not in turn.found)
            return tool_result(cards)

        try:
            async for event in self._model.stream(
                system=system, messages=history, tools=(SEARCH_TOOL,), execute=execute
            ):
                match event:
                    case TextDelta(text=chunk):
                        turn.parts.append(chunk)
                        yield StreamEvent("delta", {"text": chunk})
                    case ToolInvocation():
                        continue
                    case Usage():
                        turn.usage = event
        except DomainError as error:
            await sync_to_async(self._finish)(
                actor, session, question, turn, started=started, error_code=error.code
            )
            yield StreamEvent("error", {"code": error.code, "detail": str(error.detail)})
            return
        if turn.found:
            cards = await sync_to_async(self._search.cards)(actor, turn.found)
            yield StreamEvent("products", {"products": [asdict(card) for card in cards]})
        reply = await sync_to_async(self._finish)(
            actor, session, question, turn, started=started, error_code=""
        )
        yield StreamEvent(
            "done",
            {
                "message_id": reply.pk,
                "session_id": str(session.pk),
                "usage": {
                    "input_tokens": turn.usage.input_tokens,
                    "output_tokens": turn.usage.output_tokens,
                },
            },
        )

    def _finish(
        self,
        actor: Actor,
        session: AssistantSession,
        question: AssistantMessage,
        turn: "_Turn",
        *,
        started: float,
        error_code: str,
    ) -> AssistantMessage:
        return self._store.finish(
            actor,
            session,
            question,
            answer="".join(turn.parts).strip(),
            product_ids=turn.found,
            tool_calls=turn.calls,
            usage=turn.usage,
            cost=turn.usage.cost(input_price=self._input_price, output_price=self._output_price),
            latency_ms=int((self._clock() - started) * 1000),
            error_code=error_code,
        )


@dataclass(frozen=True, slots=True)
class PendingTurn:
    session: AssistantSession
    question: AssistantMessage


class _Turn:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.found: list[int] = []
        self.calls: list[dict[str, Any]] = []
        self.usage = Usage()


def _query(arguments: dict[str, Any], *, fallback: str) -> ProductQuery:
    max_price = arguments.get("max_price")
    return ProductQuery(
        query=str(arguments.get("query") or fallback),
        category=str(arguments["category"]) if arguments.get("category") else None,
        on_sale=bool(arguments["on_sale"]) if arguments.get("on_sale") is not None else None,
        max_price=Decimal(str(max_price)) if max_price is not None else None,
    )

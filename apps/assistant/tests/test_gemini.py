from types import SimpleNamespace
from typing import Any, cast

import pytest
from asgiref.sync import async_to_sync
from google import genai
from google.genai import errors, types

from apps.assistant.adapters.gemini import GeminiChatModel, GeminiEmbedder
from apps.assistant.domain.conversation import (
    ChatMessage,
    TextDelta,
    ToolInvocation,
    ToolSpec,
    Usage,
)
from apps.assistant.domain.enums import EmbeddingTask, Role
from apps.assistant.domain.errors import AssistantUnavailable

TOOL = ToolSpec("search_products", "Recherche", {"type": "object", "properties": {}})


def chunk(
    *parts: types.Part, usage: tuple[int, int] | None = None
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=usage[0], candidates_token_count=usage[1]
        )
        if usage
        else None,
    )


class Stream:
    def __init__(self, chunks: list[types.GenerateContentResponse]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self) -> "Stream":
        return self

    async def __anext__(self) -> types.GenerateContentResponse:
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeClient:
    def __init__(self, rounds: list[list[types.GenerateContentResponse]], *, fail: bool = False):
        self.rounds = iter(rounds)
        self.requests: list[dict[str, Any]] = []
        self.fail = fail
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content_stream=self._stream))
        self.models = SimpleNamespace(generate_content=self._generate, embed_content=self._embed)

    async def _stream(self, **request: Any) -> Stream:
        self.requests.append(request)
        if self.fail:
            raise errors.APIError(503, {"error": {"message": "overloaded"}})
        return Stream(next(self.rounds))

    def _generate(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(text='{"sentiment": "positive"}')

    def _embed(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1, 0.2]) for _ in request["contents"]]
        )


def as_client(client: FakeClient) -> genai.Client:
    return cast("genai.Client", client)


def collect(model: GeminiChatModel, executed: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    async def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        executed.append((name, arguments))
        return {"products": [{"name": "Galaxy"}]}

    async def run() -> list[Any]:
        return [
            event
            async for event in model.stream(
                system="Tu es l'assistant.",
                messages=[ChatMessage(Role.USER, "Un téléphone ?")],
                tools=(TOOL,),
                execute=execute,
            )
        ]

    return async_to_sync(run)()


def test_function_calls_are_executed_then_the_answer_streams():
    call = types.Part(
        function_call=types.FunctionCall(name="search_products", args={"query": "téléphone"})
    )
    client = FakeClient(
        [
            [chunk(call, usage=(100, 5))],
            [
                chunk(types.Part.from_text(text="Je vous propose "), usage=(180, 10)),
                chunk(types.Part.from_text(text="le Galaxy."), usage=(180, 20)),
            ],
        ]
    )
    executed: list[tuple[str, dict[str, Any]]] = []

    events = collect(
        GeminiChatModel(as_client(client), "gemini-2.5-flash", max_tool_rounds=2), executed
    )

    assert executed == [("search_products", {"query": "téléphone"})]
    assert isinstance(events[0], ToolInvocation)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [
        "Je vous propose ",
        "le Galaxy.",
    ]
    assert events[-1] == Usage(input_tokens=180, output_tokens=20)
    second = client.requests[1]["contents"]
    assert second[-1].parts[0].function_response.name == "search_products"
    assert client.requests[0]["config"].system_instruction == "Tu es l'assistant."


def test_api_errors_become_domain_errors():
    model = GeminiChatModel(
        as_client(FakeClient([], fail=True)), "gemini-2.5-flash", max_tool_rounds=1
    )

    with pytest.raises(AssistantUnavailable):
        collect(model, [])


def test_completion_and_embeddings():
    client = FakeClient([])
    model = GeminiChatModel(as_client(client), "gemini-2.5-flash", max_tool_rounds=1)
    embedder = GeminiEmbedder(as_client(client), "gemini-embedding-001")

    assert model.complete(system="", prompt="Analyse") == '{"sentiment": "positive"}'
    assert embedder.embed(["a", "b"], task=EmbeddingTask.QUERY) == [[0.1, 0.2], [0.1, 0.2]]
    assert client.requests[-1]["config"].task_type == "RETRIEVAL_QUERY"
    assert client.requests[-1]["config"].output_dimensionality == 768

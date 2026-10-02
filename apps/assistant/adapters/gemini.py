from collections.abc import AsyncIterator, Sequence
from typing import Any

from google import genai
from google.genai import errors, types

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
from apps.assistant.domain.enums import EmbeddingTask, Role
from apps.assistant.domain.errors import AssistantUnavailable

TASKS = {EmbeddingTask.DOCUMENT: "RETRIEVAL_DOCUMENT", EmbeddingTask.QUERY: "RETRIEVAL_QUERY"}


class GeminiChatModel:
    def __init__(self, client: genai.Client, model: str, *, max_tool_rounds: int) -> None:
        self._client = client
        self.name = model
        self._max_tool_rounds = max_tool_rounds

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        execute: ToolExecutor,
    ) -> AsyncIterator[ChatEvent]:
        contents: list[types.ContentUnion] = [_content(message) for message in messages]
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[_declaration(tool) for tool in tools])]
            if tools
            else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        usage = Usage()
        try:
            for round_number in range(self._max_tool_rounds + 1):
                calls: list[types.FunctionCall] = []
                stream = await self._client.aio.models.generate_content_stream(
                    model=self.name, contents=contents, config=config
                )
                async for chunk in stream:
                    usage = _usage(chunk, usage)
                    for part in _parts(chunk):
                        if part.function_call is not None:
                            calls.append(part.function_call)
                        elif part.text:
                            yield TextDelta(part.text)
                if not calls or round_number == self._max_tool_rounds:
                    break
                contents.append(
                    types.Content(
                        role="model", parts=[types.Part(function_call=call) for call in calls]
                    )
                )
                responses = []
                for call in calls:
                    arguments = dict(call.args or {})
                    result = await execute(call.name or "", arguments)
                    yield ToolInvocation(call.name or "", arguments, result)
                    responses.append(
                        types.Part.from_function_response(name=call.name or "", response=result)
                    )
                contents.append(types.Content(role="user", parts=responses))
        except errors.APIError as error:
            raise AssistantUnavailable from error
        yield usage

    def complete(self, *, system: str, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self.name,
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system or None),
            )
        except errors.APIError as error:
            raise AssistantUnavailable from error
        return response.text or ""


class GeminiEmbedder:
    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self.name = model

    def embed(self, texts: Sequence[str], *, task: EmbeddingTask) -> list[list[float]]:
        try:
            response = self._client.models.embed_content(
                model=self.name,
                contents=list[types.ContentUnion](texts),
                config=types.EmbedContentConfig(
                    task_type=TASKS[task], output_dimensionality=EMBEDDING_DIMENSIONS
                ),
            )
        except errors.APIError as error:
            raise AssistantUnavailable from error
        return [list(embedding.values or []) for embedding in response.embeddings or []]


def _content(message: ChatMessage) -> types.Content:
    role = "model" if message.role is Role.ASSISTANT else "user"
    return types.Content(role=role, parts=[types.Part.from_text(text=message.text)])


def _declaration(tool: ToolSpec) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=tool.name, description=tool.description, parameters_json_schema=tool.parameters
    )


def _parts(chunk: types.GenerateContentResponse) -> list[types.Part]:
    candidates = chunk.candidates or []
    content = candidates[0].content if candidates else None
    return list(content.parts or []) if content else []


def _usage(chunk: types.GenerateContentResponse, current: Usage) -> Usage:
    metadata: Any = chunk.usage_metadata
    if metadata is None:
        return current
    return Usage(
        input_tokens=int(metadata.prompt_token_count or current.input_tokens),
        output_tokens=int(metadata.candidates_token_count or current.output_tokens),
    )

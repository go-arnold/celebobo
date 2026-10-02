import json
from collections.abc import AsyncIterator
from typing import Any

from asgiref.sync import async_to_sync
from django.core.serializers.json import DjangoJSONEncoder
from django.http import StreamingHttpResponse

from apps.assistant.domain.conversation import StreamEvent


def jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


async def sse(events: AsyncIterator[StreamEvent]) -> AsyncIterator[bytes]:
    yield b": stream\n\n"
    async for event in events:
        payload = json.dumps(event.data, cls=DjangoJSONEncoder, ensure_ascii=False)
        yield f"event: {event.name}\ndata: {payload}\n\n".encode()


def event_stream(events: AsyncIterator[StreamEvent]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(sse(events), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def collect(events: AsyncIterator[StreamEvent]) -> dict[str, Any]:
    async def gather() -> list[StreamEvent]:
        return [event async for event in events]

    reply: dict[str, Any] = {"content": "", "products": [], "error": None}
    for event in async_to_sync(gather)():
        match event.name:
            case "delta":
                reply["content"] += event.data["text"]
            case "products":
                reply["products"] = event.data["products"]
            case "error":
                reply["error"] = event.data
            case "done":
                reply.update(event.data)
    reply["content"] = reply["content"].strip()
    result: dict[str, Any] = jsonable(reply)
    return result

import json
from typing import Any

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.assistant.domain.errors import AssistantUnavailable
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.assistant.services.contracts import ChatModel
from apps.assistant.tests.conftest import ScriptedModel
from core.container import container

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/assistant/sessions/"


def open_session(api) -> str:
    response = api.post(SESSIONS)
    assert response.status_code == 201, response.json()
    return str(response.json()["id"])


def ask(api, session_id: str, content: str, *, stream: bool = False):
    url = f"{SESSIONS}{session_id}/messages/" + ("" if stream else "?stream=false")
    return api.post(url, {"content": content}, format="json")


def events(response) -> list[tuple[str, dict[str, Any]]]:
    body = b"".join(response).decode()
    parsed = []
    for block in body.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if lines:
            parsed.append((lines["event"], json.loads(lines["data"])))
    return parsed


class TestConversation:
    def test_anonymous_visitors_chat_with_product_grounding(self, api, catalogue, scripted):
        session_id = open_session(api)

        body = ask(api, session_id, "Un smartphone Samsung à moins de 300 $ ?").json()

        assert body["content"].startswith("Bonjour ! Je vous conseille : Samsung Galaxy A55")
        assert [product["name"] for product in body["products"]][:2] == [
            "Samsung Galaxy A55",
            "Xiaomi Redmi Note 13",
        ]
        assert all(float(product["current_price"]) <= 300 for product in body["products"])
        assert body["usage"] == {"input_tokens": 1200, "output_tokens": 300}
        reply = AssistantMessage.objects.get(pk=body["message_id"])
        assert str(reply.cost) == "0.001110"
        assert reply.tool_calls == [
            {
                "name": "search_products",
                "arguments": {"query": "smartphone samsung", "max_price": 300},
            }
        ]
        session = AssistantSession.objects.get(pk=session_id)
        assert session.title == "Un smartphone Samsung à moins de 300 $ ?"
        assert session.message_count == 2

    def test_replies_stream_as_server_sent_events(self, api, catalogue, scripted):
        session_id = open_session(api)

        response = ask(api, session_id, "Quel smartphone ?", stream=True)

        assert response["Content-Type"] == "text/event-stream"
        names = [name for name, _ in events(response)]
        assert names == ["delta", "delta", "products", "done"]

    def test_history_is_sent_back_to_the_model(self, api, catalogue, scripted):
        session_id = open_session(api)
        ask(api, session_id, "Bonjour")
        ask(api, session_id, "Et moins cher ?")

        _, messages = scripted.seen[-1]
        assert messages[0].text == "Bonjour"
        assert messages[-1].text == "Et moins cher ?"
        assert len(messages) == 3

    def test_offline_provider_answers_from_the_catalogue(self, api, catalogue):
        session_id = open_session(api)

        body = ask(api, session_id, "coque de protection").json()

        assert "Coque silicone" in body["content"]
        assert body["products"][0]["name"] == "Coque silicone"

    def test_model_failures_end_the_stream_cleanly(self, api, catalogue):
        failing = ScriptedModel(fail=AssistantUnavailable())
        session_id = open_session(api)

        with container.override(ChatModel, failing):
            response = ask(api, session_id, "Bonjour", stream=True)
            parsed = events(response)

        assert parsed[-1] == (
            "error",
            {
                "code": "assistant_unavailable",
                "detail": "L'assistant est momentanément indisponible.",
            },
        )
        reply = AssistantMessage.objects.get(role="assistant")
        assert reply.error_code == "assistant_unavailable"
        assert AssistantSession.objects.get(pk=session_id).message_count == 1


class TestSessions:
    def test_signed_in_users_keep_their_history(self, as_user, shopper, catalogue, scripted):
        api = as_user(shopper)
        session_id = open_session(api)
        ask(api, session_id, "Bonjour")

        listing = api.get(SESSIONS).json()
        detail = api.get(f"{SESSIONS}{session_id}/").json()

        assert listing["meta"]["count"] == 1
        assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
        assert detail["messages"][1]["product_ids"]

    def test_sessions_are_private(self, as_user, shopper, catalogue, scripted):
        session_id = open_session(as_user(shopper))
        stranger = as_user(UserFactory.create())

        assert stranger.get(f"{SESSIONS}{session_id}/").status_code == 404
        assert ask(stranger, session_id, "Bonjour").status_code == 404
        assert stranger.delete(f"{SESSIONS}{session_id}/").status_code == 404

    def test_anonymous_visitors_have_no_history_listing(self, api):
        assert api.get(SESSIONS).status_code in (401, 403)

    def test_owners_can_delete_a_session(self, as_user, shopper):
        api = as_user(shopper)
        session_id = open_session(api)

        assert api.delete(f"{SESSIONS}{session_id}/").status_code == 204
        assert not AssistantSession.objects.exists()


class TestLimits:
    def test_questions_have_a_maximum_length(self, api):
        session_id = open_session(api)

        response = ask(api, session_id, "x" * 1001)

        assert response.status_code == 400
        assert response.json()["code"] == "question_too_long"

    def test_daily_quota(self, api, catalogue, scripted, settings):
        settings.ASSISTANT = {"PROVIDER": "offline", "DAILY_MESSAGES": 1}
        session_id = open_session(api)
        ask(api, session_id, "Bonjour")

        response = ask(api, session_id, "Encore une question")

        assert response.status_code == 503
        assert response.json()["code"] == "assistant_quota_exceeded"


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_streaming_over_asgi(async_client):
    from asgiref.sync import sync_to_async

    from apps.assistant.facades import AssistantInsightsFacade
    from apps.catalog.tests.factories import ProductFactory

    product = await sync_to_async(ProductFactory.create)(name="Coque silicone")
    await sync_to_async(container.resolve(AssistantInsightsFacade).refresh_embeddings)([product.pk])
    session = await async_client.post(SESSIONS)
    session_id = session.json()["id"]

    response = await async_client.post(
        f"{SESSIONS}{session_id}/messages/",
        {"content": "coque"},
        content_type="application/json",
    )

    chunks = [chunk async for chunk in response.streaming_content]
    body = b"".join(chunks).decode()
    assert response["Content-Type"] == "text/event-stream"
    assert len(chunks) > 3
    assert "event: products" in body
    assert body.rstrip().splitlines()[-2] == "event: done"

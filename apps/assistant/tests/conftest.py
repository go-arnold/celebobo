from collections.abc import AsyncIterator, Iterator, Sequence
from decimal import Decimal
from typing import Any

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import AdminFactory, ManagerFactory
from apps.assistant.domain.conversation import (
    ChatEvent,
    ChatMessage,
    TextDelta,
    ToolExecutor,
    ToolSpec,
    Usage,
)
from apps.assistant.facades import AssistantInsightsFacade
from apps.assistant.services.contracts import ChatModel
from apps.catalog.models import Product
from apps.catalog.tests.factories import CategoryFactory, ProductFactory
from apps.orders.tests.conftest import api, as_user, shopper
from core.container import container

__all__ = ["api", "as_user", "shopper"]


@pytest.fixture
def manager(db) -> User:
    return ManagerFactory.create()


@pytest.fixture
def admin(db) -> User:
    return AdminFactory.create()


@pytest.fixture
def catalogue(db) -> dict[str, Product]:
    phones = CategoryFactory.create(name="Smartphones", slug="smartphones")
    accessories = CategoryFactory.create(name="Accessoires", slug="accessoires")
    products = {
        "galaxy": ProductFactory.create(
            name="Samsung Galaxy A55",
            description="Smartphone Samsung 5G, écran AMOLED et triple caméra.",
            category=phones,
            price=Decimal("320.00"),
            sale_price=Decimal("299.00"),
        ),
        "redmi": ProductFactory.create(
            name="Xiaomi Redmi Note 13",
            description="Smartphone Xiaomi avec grande batterie.",
            category=phones,
            price=Decimal("180.00"),
        ),
        "case": ProductFactory.create(
            name="Coque silicone",
            description="Coque de protection souple pour téléphone.",
            category=accessories,
            price=Decimal("8.00"),
        ),
    }
    container.resolve(AssistantInsightsFacade).refresh_embeddings(
        [product.pk for product in products.values()]
    )
    return products


class ScriptedModel:
    name = "scripted"

    def __init__(
        self, *, tool_arguments: dict[str, Any] | None = None, fail: Exception | None = None
    ):
        self.tool_arguments = tool_arguments
        self.fail = fail
        self.seen: list[tuple[str, list[ChatMessage]]] = []
        self.completions: list[str] = []

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[ChatMessage],
        tools: Sequence[ToolSpec],
        execute: ToolExecutor,
    ) -> AsyncIterator[ChatEvent]:
        self.seen.append((system, list(messages)))
        if self.tool_arguments is not None:
            result = await execute(tools[0].name, self.tool_arguments)
            names = ", ".join(item["name"] for item in result["products"])
        else:
            names = ""
        yield TextDelta("Bonjour ! ")
        if self.fail is not None:
            raise self.fail
        yield TextDelta(f"Je vous conseille : {names}." if names else "Comment puis-je aider ?")
        yield Usage(input_tokens=1200, output_tokens=300)

    def complete(self, *, system: str, prompt: str) -> str:
        self.completions.append(prompt)
        if "JSON" in prompt:
            return 'Voici : {"sentiment": "negative", "topic": "Livraison"}'
        return "Le client cherche un smartphone à moins de 300 $."


@pytest.fixture
def scripted() -> Iterator[ScriptedModel]:
    model = ScriptedModel(tool_arguments={"query": "smartphone samsung", "max_price": 300})
    with container.override(ChatModel, model):
        yield model

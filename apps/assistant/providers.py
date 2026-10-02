from django.utils import timezone

from apps.assistant.adapters.gateways import CatalogCards, CatalogDocuments
from apps.assistant.adapters.offline import HashingEmbedder, OfflineChatModel
from apps.assistant.conf import AssistantSettings, assistant_settings
from apps.assistant.facades import AssistantFacade, AssistantInsightsFacade
from apps.assistant.repositories import EmbeddingRepository, MessageRepository, SessionRepository
from apps.assistant.selectors import LogSelector, SessionSelector, VectorSelector
from apps.assistant.services.chat import ChatService
from apps.assistant.services.contracts import ChatModel, Embedder, ProductCards, ProductDocuments
from apps.assistant.services.conversations import ConversationStore
from apps.assistant.services.embeddings import EmbeddingService
from apps.assistant.services.followups import InsightService, MemoryService
from apps.assistant.services.search import ProductSearch
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher
from core.registry import Registry

chat_models: Registry[ChatModel] = Registry("assistant chat model")
embedders: Registry[Embedder] = Registry("assistant embedder")


def _gemini_client(settings: AssistantSettings):  # type: ignore[no-untyped-def]
    from google import genai

    return genai.Client(api_key=settings.api_key)


def _gemini_chat() -> ChatModel:
    from apps.assistant.adapters.gemini import GeminiChatModel

    settings = assistant_settings()
    return GeminiChatModel(
        _gemini_client(settings), settings.chat_model, max_tool_rounds=settings.max_tool_rounds
    )


def _gemini_embedder() -> Embedder:
    from apps.assistant.adapters.gemini import GeminiEmbedder

    settings = assistant_settings()
    return GeminiEmbedder(_gemini_client(settings), settings.embedding_model)


chat_models.add("offline", OfflineChatModel)
chat_models.add("gemini", _gemini_chat)
embedders.add("offline", HashingEmbedder)
embedders.add("gemini", _gemini_embedder)


def register(container: Container) -> None:
    container.register(ChatModel, lambda _: chat_models.create(assistant_settings().provider))
    container.register(Embedder, lambda _: embedders.create(assistant_settings().provider))
    container.register(ProductDocuments, lambda _: CatalogDocuments())
    container.register(ProductCards, lambda _: CatalogCards())
    container.register(AssistantFacade, _assistant_facade, lifetime=Lifetime.TRANSIENT)
    container.register(AssistantInsightsFacade, _insights_facade, lifetime=Lifetime.TRANSIENT)


def _assistant_facade(container: Container) -> AssistantFacade:
    settings = assistant_settings()
    store = ConversationStore(
        SessionRepository(),
        MessageRepository(),
        container.resolve(EventPublisher),
        memory_messages=settings.memory_messages,
        max_question_length=settings.max_question_length,
        daily_messages=settings.daily_messages,
        clock=timezone.now,
    )
    search = ProductSearch(
        VectorSelector(),
        container.resolve(Embedder),
        container.resolve(ProductCards),
        limit=settings.search_limit,
    )
    return AssistantFacade(
        store=store,
        chat=ChatService(
            store,
            container.resolve(ChatModel),
            search,
            input_price=settings.input_cost,
            output_price=settings.output_cost,
        ),
        sessions=SessionSelector(),
    )


def _insights_facade(container: Container) -> AssistantInsightsFacade:
    settings = assistant_settings()
    messages = MessageRepository()
    model = container.resolve(ChatModel)
    return AssistantInsightsFacade(
        logs=LogSelector(),
        insights=InsightService(messages, model),
        memory=MemoryService(
            SessionRepository(),
            messages,
            model,
            memory_messages=settings.memory_messages,
            summary_every=settings.summary_every,
        ),
        embeddings=EmbeddingService(
            EmbeddingRepository(), container.resolve(ProductDocuments), container.resolve(Embedder)
        ),
        publisher=container.resolve(EventPublisher),
    )

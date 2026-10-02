from apps.assistant.adapters.gateways import CatalogDocuments
from apps.assistant.domain.events import AssistantReplied, EmbeddingsReindexRequested
from apps.assistant.facades import AssistantInsightsFacade
from apps.catalog.domain.events import CategoryChanged, ProductChanged, ProductRemoved
from core.container import container
from core.events.bus import event_bus


def _insights() -> AssistantInsightsFacade:
    return container.resolve(AssistantInsightsFacade)


@event_bus.on(ProductChanged, ProductRemoved, background=True)
def embed_product(event: ProductChanged | ProductRemoved) -> None:
    _insights().refresh_embeddings([event.product_id])


@event_bus.on(CategoryChanged, background=True)
def embed_category(event: CategoryChanged) -> None:
    _insights().refresh_embeddings(CatalogDocuments().category_ids(event.category_id))


@event_bus.on(EmbeddingsReindexRequested, background=True)
def reindex_embeddings(_event: EmbeddingsReindexRequested) -> None:
    _insights().reindex()


@event_bus.on(AssistantReplied, background=True)
def follow_up_reply(event: AssistantReplied) -> None:
    _insights().follow_up(event.session_id, event.question_id)

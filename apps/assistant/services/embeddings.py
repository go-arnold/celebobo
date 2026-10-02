import hashlib
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from apps.assistant.domain.enums import EmbeddingTask
from apps.assistant.repositories import EmbeddingRepository
from apps.assistant.services.contracts import Embedder, ProductDocuments

BATCH = 50


def embedded_text(document: dict[str, Any]) -> str:
    parts = [
        document["name"],
        f"Catégorie : {document['category_name']}",
        document.get("description") or "",
        "Caractéristiques : " + ", ".join(document.get("features") or []),
    ]
    return "\n".join(part for part in parts if part.strip())


class EmbeddingService:
    def __init__(
        self, embeddings: EmbeddingRepository, documents: ProductDocuments, embedder: Embedder
    ) -> None:
        self._embeddings = embeddings
        self._documents = documents
        self._embedder = embedder

    def refresh(self, product_ids: Sequence[int]) -> dict[str, int]:
        documents = {
            document["id"]: document for document in self._documents.documents(product_ids)
        }
        removed = self._embeddings.delete(set(product_ids) - set(documents))
        known = self._embeddings.hashes(documents)
        stale: list[tuple[dict[str, Any], str, str]] = []
        for document in documents.values():
            text = embedded_text(document)
            digest = hashlib.sha256(f"{self._embedder.name}\n{text}".encode()).hexdigest()
            if known.get(document["id"]) == digest:
                self._embeddings.update_metadata(document["id"], **_metadata(document))
            else:
                stale.append((document, text, digest))
        for start in range(0, len(stale), BATCH):
            batch = stale[start : start + BATCH]
            vectors = self._embedder.embed(
                [text for _, text, _ in batch], task=EmbeddingTask.DOCUMENT
            )
            for (document, text, digest), vector in zip(batch, vectors, strict=True):
                self._embeddings.upsert(
                    document["id"],
                    embedding=vector,
                    embedded_text=text,
                    content_hash=digest,
                    model_name=self._embedder.name,
                    **_metadata(document),
                )
        return {
            "embedded": len(stale),
            "removed": removed,
            "unchanged": len(documents) - len(stale),
        }

    def reindex(self) -> dict[str, int]:
        ids = self._documents.all_ids()
        totals = {"embedded": 0, "removed": 0, "unchanged": 0}
        for start in range(0, len(ids), BATCH * 4):
            for key, value in self.refresh(ids[start : start + BATCH * 4]).items():
                totals[key] += value
        return totals


def _metadata(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "category_slug": document["category_slug"],
        "current_price": Decimal(str(document["current_price"])).quantize(Decimal("0.01")),
        "on_sale": bool(document["on_sale"]),
        "in_stock": bool(document["in_stock"]),
    }

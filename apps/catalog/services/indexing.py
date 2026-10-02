from collections.abc import Sequence

from apps.catalog.selectors import ProductDocumentSelector
from apps.catalog.services.contracts import SearchIndex


class ProductIndexer:
    def __init__(self, index: SearchIndex, documents: ProductDocumentSelector) -> None:
        self._index = index
        self._documents = documents

    def sync(self, product_ids: Sequence[int]) -> None:
        documents = self._documents.documents(product_ids)
        indexed = {document["id"] for document in documents}
        if documents:
            self._index.upsert(documents)
        if stale := [pk for pk in product_ids if pk not in indexed]:
            self._index.remove(stale)

    def sync_category(self, category_id: int) -> None:
        self.sync(self._documents.ids_in_category(category_id))

    def remove(self, product_ids: Sequence[int]) -> None:
        self._index.remove(product_ids)

    def rebuild(self) -> int:
        self._index.configure()
        total = 0
        for batch in self._documents.all_ids():
            self.sync(batch)
            total += len(batch)
        return total

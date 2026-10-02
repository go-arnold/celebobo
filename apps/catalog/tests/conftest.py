from collections.abc import Iterator, Sequence

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.catalog.domain.read_models import ProductDocument
from apps.catalog.services.contracts import PurchaseVerifier, SearchIndex
from apps.catalog.services.indexing import ProductIndexer
from core.container import container


class RecordingIndex:
    def __init__(self) -> None:
        self.documents: dict[int, ProductDocument] = {}
        self.removed: list[int] = []
        self.configured = 0

    def configure(self) -> None:
        self.configured += 1

    def upsert(self, documents: Sequence[ProductDocument]) -> None:
        self.documents.update({document["id"]: document for document in documents})

    def remove(self, product_ids: Sequence[int]) -> None:
        self.removed.extend(product_ids)
        for product_id in product_ids:
            self.documents.pop(product_id, None)


class AllowListPurchases:
    def __init__(self) -> None:
        self.received: set[tuple[int, int]] = set()

    def has_received(self, user_id: int, product_id: int) -> bool:
        return (user_id, product_id) in self.received


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def shopper(db) -> User:
    return UserFactory.create(first_name="Aline", last_name="Mbuyi")


@pytest.fixture
def as_user(api: APIClient):
    def authenticate(user: User) -> APIClient:
        api.force_authenticate(user)
        return api

    return authenticate


@pytest.fixture
def search_index() -> Iterator[RecordingIndex]:
    index = RecordingIndex()
    with container.override(SearchIndex, index):
        yield index


@pytest.fixture
def purchases() -> Iterator[AllowListPurchases]:
    verifier = AllowListPurchases()
    with container.override(PurchaseVerifier, verifier):
        yield verifier


@pytest.fixture
def reindex():
    def run() -> int:
        return container.resolve(ProductIndexer).rebuild()

    return run

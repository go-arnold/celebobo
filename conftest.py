from collections.abc import Iterator

import pytest
from django.core.cache import cache

pytest_plugins = ["core.testing.fixtures"]


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    cache.clear()
    yield
    cache.clear()

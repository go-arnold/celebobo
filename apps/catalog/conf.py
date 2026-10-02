from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    search_engine: str = "database"
    search_index: str = "null"
    new_product_days: int = 20
    cache_ttl: int = 300
    page_size: int = 12
    max_page_size: int = 48
    suggestion_limit: int = 6
    related_limit: int = 8


@dataclass(frozen=True, slots=True)
class MeilisearchSettings:
    url: str = "http://localhost:7700"
    api_key: str = ""
    index: str = "products"
    timeout: int = 2


def catalog_settings() -> CatalogSettings:
    return load_section("CATALOG", CatalogSettings)


def meilisearch_settings() -> MeilisearchSettings:
    return load_section("MEILISEARCH", MeilisearchSettings)

from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    search_engine: str = "postgres"
    search_index: str = "postgres"
    search_config: str = "french_unaccent"
    new_product_days: int = 20
    cache_ttl: int = 300
    page_size: int = 12
    max_page_size: int = 48
    suggestion_limit: int = 6
    related_limit: int = 8


def catalog_settings() -> CatalogSettings:
    return load_section("CATALOG", CatalogSettings)

from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class StorefrontSettings:
    revalidate_url: str = ""
    revalidate_secret: str = ""
    revalidate_timeout: float = 5.0
    revalidate_retries: int = 3
    # sent once changes stop for `debounce` seconds, at most `max_wait` after the first one
    debounce: int = 5
    max_wait: int = 60


def storefront_settings() -> StorefrontSettings:
    return load_section("STOREFRONT", StorefrontSettings)

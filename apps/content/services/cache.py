from core.cache import VersionedCache


class ContentCache(VersionedCache):
    def __init__(self) -> None:
        # bump the suffix whenever a cached read model changes shape
        super().__init__("content:2", ttl=600)

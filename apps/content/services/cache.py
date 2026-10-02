from core.cache import VersionedCache


class ContentCache(VersionedCache):
    def __init__(self) -> None:
        super().__init__("content", ttl=600)

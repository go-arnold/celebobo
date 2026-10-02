from collections.abc import Collection
from typing import Protocol

from core.registry import Registry


class MediaReferences(Protocol):
    def referenced(self, urls: Collection[str]) -> set[str]: ...


media_references: Registry[MediaReferences] = Registry("media references")


def referenced(urls: Collection[str]) -> set[str]:
    used: set[str] = set()
    for name in media_references:
        used |= media_references.create(name).referenced(urls)
    return used

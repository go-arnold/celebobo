from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    label: str
    numeric: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Table:
    title: str
    columns: Sequence[Column]
    rows: Sequence[Sequence[Any]]
    subtitle: str = ""
    totals: Sequence[tuple[str, str]] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True, kw_only=True)
class RenderedFile:
    content: bytes
    filename: str
    content_type: str

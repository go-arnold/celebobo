"""Celebobo's policies: the text first loaded into the site pages, then edited in the back-office.

Each file has a small header (title, summary, version, effective_on, position) and a Markdown body.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

POLICY_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class PolicySource:
    slug: str
    title: str
    summary: str
    version: str
    effective_on: date
    position: int
    body: str


def read(path: Path) -> PolicySource:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    _, header, body = text.split("---\n", 2)
    fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
    return PolicySource(
        slug=path.stem,
        title=fields["title"],
        summary=fields["summary"],
        version=fields["version"],
        effective_on=date.fromisoformat(fields["effective_on"]),
        position=int(fields["position"]),
        body=body.strip(),
    )


def policies() -> list[PolicySource]:
    return sorted((read(path) for path in POLICY_DIR.glob("*.md")), key=lambda p: p.position)

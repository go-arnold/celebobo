from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class DeliveryOutcome(StrEnum):
    DELIVERED = "delivered"
    GONE = "gone"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class PushMessage:
    title: str
    body: str
    url: str
    tag: str = ""

    def payload(self) -> dict[str, str]:
        return {"title": self.title, "body": self.body, "url": self.url, "tag": self.tag}


@dataclass(frozen=True, slots=True, kw_only=True)
class Endpoint:
    url: str
    p256dh: str
    auth: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterDevice:
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceView:
    id: int
    user_agent: str
    created_at: datetime
    last_used_at: datetime | None


@dataclass(frozen=True, slots=True)
class SendResult:
    delivered: int
    removed: int
    failed: int

from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class MessagingSettings:
    notification_channels: tuple[str, ...] = ("in_app", "email")
    page_size: int = 30


def messaging_settings() -> MessagingSettings:
    return load_section("MESSAGING", MessagingSettings)

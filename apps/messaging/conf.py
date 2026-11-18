from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class MessagingSettings:
    notification_channels: tuple[str, ...] = ("in_app", "email", "push")
    page_size: int = 30
    # an order's discussion stays open this long after the order ends, then closes
    order_thread_grace_days: int = 7


def messaging_settings() -> MessagingSettings:
    return load_section("MESSAGING", MessagingSettings)

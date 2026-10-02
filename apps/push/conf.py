from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class PushSettings:
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:contact@celebobo.cd"
    ttl: int = 86_400
    max_devices: int = 10
    max_failures: int = 5

    @property
    def enabled(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key)


def push_settings() -> PushSettings:
    return load_section("PUSH", PushSettings)

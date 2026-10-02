from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class RealtimeSettings:
    burst: int = 20
    refill_per_second: float = 2.0
    presence_ttl: int = 90


def realtime_settings() -> RealtimeSettings:
    return load_section("REALTIME", RealtimeSettings)

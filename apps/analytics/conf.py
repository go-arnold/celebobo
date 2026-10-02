from dataclasses import dataclass

from core.conf import load_section


@dataclass(frozen=True, slots=True)
class AnalyticsSettings:
    refresh_debounce_seconds: int = 30
    top_limit: int = 5
    slow_mover_limit: int = 20
    widget_limit: int = 5


def analytics_settings() -> AnalyticsSettings:
    return load_section("ANALYTICS", AnalyticsSettings)

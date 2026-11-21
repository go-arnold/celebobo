from typing import Any

from django.utils import timezone

from apps.loyalty.domain.settings import LoyaltySettingsChanges
from apps.loyalty.models import LoyaltySettings
from apps.loyalty.repositories import LoyaltySettingsRepository
from core.domain.values import provided


class LoyaltySettingsService:
    def __init__(self, settings: LoyaltySettingsRepository) -> None:
        self._settings = settings

    def current(self) -> LoyaltySettings:
        return self._settings.current()

    def update(self, changes: LoyaltySettingsChanges) -> tuple[str, ...]:
        settings = self._settings.current(for_update=True)
        values: dict[str, Any] = dict(provided(changes))
        changed = tuple(name for name, value in values.items() if getattr(settings, name) != value)
        for name in changed:
            setattr(settings, name, values[name])
        saved = changed
        if "points_enabled" in changed:
            # switched off: the points stay usable for a while (loyalty policy)
            settings.points_disabled_at = None if settings.points_enabled else timezone.now()
            saved = (*changed, "points_disabled_at")
        if changed:
            self._settings.save(settings, fields=saved)
        return changed

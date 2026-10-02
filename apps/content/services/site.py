from typing import Any

from apps.content.domain.commands import SettingsChanges
from apps.content.models import SiteSettings
from apps.content.repositories import SettingsRepository
from apps.content.services.rules import known_payment_methods
from core.domain.values import provided


class SiteSettingsService:
    def __init__(self, settings: SettingsRepository) -> None:
        self._settings = settings

    def current(self) -> SiteSettings:
        return self._settings.current()

    def update(self, changes: SettingsChanges) -> tuple[SiteSettings, tuple[str, ...]]:
        settings = self._settings.current(for_update=True)
        values: dict[str, Any] = dict(provided(changes))
        if "payment_methods" in values:
            values["payment_methods"] = known_payment_methods(values["payment_methods"])
        changed = tuple(name for name, value in values.items() if getattr(settings, name) != value)
        for name in changed:
            setattr(settings, name, values[name])
        if changed:
            self._settings.save(settings, fields=changed)
        return settings, changed

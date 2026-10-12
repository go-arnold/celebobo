from collections.abc import Iterable

from apps.loyalty.models import SETTINGS_ID, LoyaltySettings


class LoyaltySettingsRepository:
    def current(self, *, for_update: bool = False) -> LoyaltySettings:
        settings = (
            LoyaltySettings.objects.select_for_update() if for_update else LoyaltySettings.objects
        )
        current, _ = settings.get_or_create(pk=SETTINGS_ID)
        return current

    def save(self, settings: LoyaltySettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from django.db.models import Model

from apps.content.models import Banner, ContactMessage, SiteSettings, Subscriber

SETTINGS_ID = 1


class ModelRepository[M: Model]:
    def __init__(self, model: type[M]) -> None:
        self._model = model

    def create(self, **fields: Any) -> M:
        return self._model._default_manager.create(**fields)

    def get(self, pk: int, *, for_update: bool = False) -> M | None:
        manager = self._model._default_manager
        queryset = manager.select_for_update() if for_update else manager.all()
        return queryset.filter(pk=pk).first()

    def save(self, instance: M, *, fields: Iterable[str]) -> None:
        instance.save(update_fields=[*fields])

    def delete(self, instance: M) -> None:
        instance.delete()

    def exists(self, **lookup: Any) -> bool:
        return self._model._default_manager.filter(**lookup).exists()


class BannerRepository(ModelRepository[Banner]):
    def __init__(self) -> None:
        super().__init__(Banner)

    def reorder(self, placement: str, ids: Sequence[int]) -> bool:
        banners = Banner.objects.select_for_update().filter(placement=placement, pk__in=ids)
        if banners.count() != len(set(ids)):
            return False
        for position, banner_id in enumerate(ids, start=1):
            Banner.objects.filter(pk=banner_id).update(position=position)
        return True


class SubscriberRepository(ModelRepository[Subscriber]):
    def __init__(self) -> None:
        super().__init__(Subscriber)

    def by_email(self, email: str, *, for_update: bool = False) -> Subscriber | None:
        queryset = Subscriber.objects.select_for_update() if for_update else Subscriber.objects
        return queryset.filter(email__iexact=email).first()

    def by_token(self, token: UUID) -> Subscriber | None:
        return Subscriber.objects.filter(token=token).first()


class SettingsRepository:
    def current(self, *, for_update: bool = False) -> SiteSettings:
        queryset = SiteSettings.objects.select_for_update() if for_update else SiteSettings.objects
        settings, _ = queryset.get_or_create(pk=SETTINGS_ID)
        return settings

    def save(self, settings: SiteSettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])


def contact_repository() -> ModelRepository[ContactMessage]:
    return ModelRepository(ContactMessage)

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db.models import Max, Model, QuerySet

from apps.audit.domain.retention import Expired
from apps.content.domain.retention import ACCOUNT_SOURCE
from apps.content.models import Banner, ContactMessage, HomeSection, SiteSettings, Subscriber

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


class SectionRepository(ModelRepository[HomeSection]):
    def __init__(self) -> None:
        super().__init__(HomeSection)

    def next_position(self) -> int:
        return int(HomeSection.objects.aggregate(top=Max("position"))["top"] or 0) + 1

    def reorder(self, ids: Sequence[int]) -> bool:
        if HomeSection.objects.filter(pk__in=ids).count() != len(set(ids)):
            return False
        for position, section_id in enumerate(ids, start=1):
            HomeSection.objects.filter(pk=section_id).update(position=position)
        return True


class SubscriberRepository(ModelRepository[Subscriber]):
    def __init__(self) -> None:
        super().__init__(Subscriber)

    def by_email(self, email: str, *, for_update: bool = False) -> Subscriber | None:
        queryset = Subscriber.objects.select_for_update() if for_update else Subscriber.objects
        return queryset.filter(email__iexact=email).first()

    def by_token(self, token: UUID) -> Subscriber | None:
        return Subscriber.objects.filter(token=token).first()

    def stale_before(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        rows = (
            _stale_before(cutoff)
            .filter(pk__gt=after_id)
            .order_by("pk")
            .values_list("pk", "subscribed_at")[:limit]
        )
        return [Expired(pk, f"abonné #{pk} inscrit le {since:%Y-%m-%d}") for pk, since in rows]

    def delete_stale(self, ids: list[int], *, before: datetime) -> int:
        _, deleted = _stale_before(before).filter(pk__in=ids).delete()
        return deleted.get(Subscriber._meta.label, 0)

    # account retention: an address that is about to disappear leaves the mailing list, unless it
    # is on the opposition list (unsubscribed), which is kept
    def delete_active(self, email: str) -> int:
        _, deleted = Subscriber.objects.filter(
            email__iexact=email, unsubscribed_at__isnull=True
        ).delete()
        return deleted.get(Subscriber._meta.label, 0)


class ContactMessageRepository:
    def received_before(self, cutoff: datetime, *, after_id: int, limit: int) -> list[Expired]:
        rows = (
            ContactMessage.objects.filter(created_at__lt=cutoff, pk__gt=after_id)
            .order_by("pk")
            .values_list("pk", "created_at")[:limit]
        )
        return [
            Expired(pk, f"message de contact #{pk} reçu le {received:%Y-%m-%d}")
            for pk, received in rows
        ]

    def delete_received_before(self, ids: list[int], *, before: datetime) -> int:
        _, deleted = ContactMessage.objects.filter(pk__in=ids, created_at__lt=before).delete()
        return deleted.get(ContactMessage._meta.label, 0)


# still subscribed, with no (re)subscription since the cutoff
def _stale_before(cutoff: datetime) -> QuerySet[Subscriber]:
    return Subscriber.objects.filter(
        unsubscribed_at__isnull=True, subscribed_at__lt=cutoff
    ).exclude(source=ACCOUNT_SOURCE)


class SettingsRepository:
    def current(self, *, for_update: bool = False) -> SiteSettings:
        queryset = SiteSettings.objects.select_for_update() if for_update else SiteSettings.objects
        settings, _ = queryset.get_or_create(pk=SETTINGS_ID)
        return settings

    def save(self, settings: SiteSettings, *, fields: Iterable[str]) -> None:
        settings.save(update_fields=[*fields, "updated_at"])


def contact_repository() -> ModelRepository[ContactMessage]:
    return ModelRepository(ContactMessage)

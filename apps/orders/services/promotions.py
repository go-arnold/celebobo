from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction

from apps.orders.domain.commands import CouponChanges, CouponFields, ZoneChanges, ZoneFields
from apps.orders.domain.errors import (
    CouponCodeTaken,
    CouponNotFound,
    ShippingZoneNotFound,
)
from apps.orders.domain.pricing import CouponKind
from apps.orders.models import Coupon, ShippingZone
from core.domain.errors import ValidationFailed
from core.domain.values import provided

MAX_PERCENT = Decimal(100)


class ShippingZoneService:
    def create(self, fields: ZoneFields) -> ShippingZone:
        values = _zone_values(asdict(fields))
        self._release_default(values)
        return ShippingZone.objects.create(**values)

    def update(self, zone_id: int, changes: ZoneChanges) -> ShippingZone:
        zone = self._get(zone_id)
        values = _zone_values(dict(provided(changes)))
        self._release_default(values, keep=zone.pk)
        return _apply(zone, values)

    def delete(self, zone_id: int) -> None:
        self._get(zone_id).delete()

    @staticmethod
    def _release_default(values: dict[str, Any], keep: int | None = None) -> None:
        if values.get("is_default"):
            others = ShippingZone.objects.filter(is_default=True)
            if keep is not None:
                others = others.exclude(pk=keep)
            others.update(is_default=False)

    @staticmethod
    def _get(zone_id: int) -> ShippingZone:
        zone = ShippingZone.objects.select_for_update().filter(pk=zone_id).first()
        if zone is None:
            raise ShippingZoneNotFound
        return zone


class CouponAdminService:
    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def create(self, fields: CouponFields) -> Coupon:
        values = asdict(fields)
        _check_coupon(values, None)
        values["code"] = values["code"].strip().upper()
        values["kind"] = values["kind"].value
        try:
            with transaction.atomic():
                return Coupon.objects.create(**values)
        except IntegrityError as error:
            raise CouponCodeTaken from error

    def update(self, coupon_id: int, changes: CouponChanges) -> Coupon:
        coupon = self._get(coupon_id)
        values = dict(provided(changes))
        _check_coupon(values, coupon)
        if "code" in values:
            values["code"] = values["code"].strip().upper()
        if "kind" in values:
            values["kind"] = values["kind"].value
        try:
            with transaction.atomic():
                return _apply(coupon, values)
        except IntegrityError as error:
            raise CouponCodeTaken from error

    def deactivate(self, coupon_id: int) -> Coupon:
        return _apply(self._get(coupon_id), {"is_active": False})

    @staticmethod
    def _get(coupon_id: int) -> Coupon:
        coupon = Coupon.objects.select_for_update().filter(pk=coupon_id).first()
        if coupon is None:
            raise CouponNotFound
        return coupon


def _zone_values(values: dict[str, Any]) -> dict[str, Any]:
    if "cities" in values:
        values["cities"] = _unique(" ".join(city.split()) for city in values["cities"])
    return values


def _check_coupon(values: dict[str, Any], coupon: Coupon | None) -> None:
    kind = values.get("kind", coupon.coupon_kind if coupon else None)
    value = values.get("value", coupon.value if coupon else None)
    starts_at = values.get("starts_at", coupon.starts_at if coupon else None)
    ends_at = values.get("ends_at", coupon.ends_at if coupon else None)
    errors: dict[str, list[str]] = {}
    if kind is CouponKind.PERCENT and value is not None and value > MAX_PERCENT:
        errors["value"] = ["Un pourcentage ne peut pas dépasser 100."]
    if starts_at and ends_at and ends_at <= starts_at:
        errors["ends_at"] = ["La fin doit suivre le début."]
    if errors:
        raise ValidationFailed(errors=errors)


def _apply[M: ShippingZone | Coupon](instance: M, values: dict[str, Any]) -> M:
    for name, value in values.items():
        setattr(instance, name, value)
    if values:
        instance.save(update_fields=list(values))
    return instance


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))

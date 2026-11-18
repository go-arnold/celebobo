import unicodedata

from apps.orders.domain.errors import PickupUnavailable
from apps.orders.domain.pricing import ShippingRules, ZonePricing
from apps.orders.models import ShippingZone
from apps.orders.repositories import ShippingZoneRepository


def normalize_city(city: str) -> str:
    plain = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace("-", " ").split())


class ShippingResolver:
    def __init__(self, zones: ShippingZoneRepository, fallback: ShippingRules) -> None:
        self._zones = zones
        self._fallback = fallback

    def rules_for(self, city: str | None, *, pickup: bool = False) -> ShippingRules:
        zones = self._zones.active()
        if pickup:
            spot = next((zone for zone in zones if zone.pricing == ZonePricing.PICKUP), None)
            if spot is None:
                raise PickupUnavailable
            return to_rules(spot)
        if not city:
            return self._fallback
        # the pickup zone is chosen, never matched from a city
        delivered = [zone for zone in zones if zone.pricing != ZonePricing.PICKUP]
        wanted = normalize_city(city)
        zone = next(
            (zone for zone in delivered if wanted in {normalize_city(n) for n in zone.cities}),
            None,
        ) or next((zone for zone in delivered if zone.is_default), None)
        return to_rules(zone) if zone else self._fallback

    def pickup_available(self) -> bool:
        return any(zone.pricing == ZonePricing.PICKUP for zone in self._zones.active())


def to_rules(zone: ShippingZone) -> ShippingRules:
    return ShippingRules(
        free_threshold=zone.free_threshold,
        flat_fee=zone.fee,
        zone=zone.name,
        delivery_estimate=zone.delivery_estimate,
        member_free=zone.member_free_shipping,
        pricing=ZonePricing(zone.pricing),
        pickup_address=zone.pickup_address,
    )

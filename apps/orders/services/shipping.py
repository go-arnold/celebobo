import unicodedata

from apps.orders.domain.pricing import ShippingRules
from apps.orders.models import ShippingZone
from apps.orders.repositories import ShippingZoneRepository


def normalize_city(city: str) -> str:
    plain = unicodedata.normalize("NFKD", city).encode("ascii", "ignore").decode()
    return " ".join(plain.lower().replace("-", " ").split())


class ShippingResolver:
    def __init__(self, zones: ShippingZoneRepository, fallback: ShippingRules) -> None:
        self._zones = zones
        self._fallback = fallback

    def rules_for(self, city: str | None) -> ShippingRules:
        if not city:
            return self._fallback
        zones = self._zones.active()
        wanted = normalize_city(city)
        zone = next(
            (zone for zone in zones if wanted in {normalize_city(name) for name in zone.cities}),
            None,
        ) or next((zone for zone in zones if zone.is_default), None)
        return to_rules(zone) if zone else self._fallback


def to_rules(zone: ShippingZone) -> ShippingRules:
    return ShippingRules(
        free_threshold=zone.free_threshold,
        flat_fee=zone.fee,
        zone=zone.name,
        delivery_estimate=zone.delivery_estimate,
    )

from dataclasses import dataclass
from decimal import Decimal

from apps.orders.domain.pricing import ShippingRules
from core.conf import load_section


@dataclass(frozen=True, slots=True)
class OrderSettings:
    free_shipping_threshold: str = "199.00"
    flat_shipping_fee: str = "2.98"
    max_lines: int = 30
    max_quantity: int = 10
    cart_ttl_days: int = 30

    @property
    def shipping_rules(self) -> ShippingRules:
        return ShippingRules(
            free_threshold=Decimal(self.free_shipping_threshold),
            flat_fee=Decimal(self.flat_shipping_fee),
        )


def order_settings() -> OrderSettings:
    return load_section("ORDERS", OrderSettings)

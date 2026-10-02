from collections.abc import Mapping, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.domain.errors import InvalidPricing, InvalidVariantAttributes, SellByInPast
from apps.catalog.domain.management import OptionInput

CENT = Decimal("0.01")
MAX_DISCOUNT_PERCENT = Decimal(90)


def validate_pricing(
    price: Decimal, sale_price: Decimal | None, cost_price: Decimal | None
) -> None:
    errors: dict[str, list[str]] = {}
    if price <= 0:
        errors["price"] = ["Le prix doit être supérieur à 0."]
    if sale_price is not None and not 0 < sale_price < price:
        errors["sale_price"] = ["Le prix soldé doit être positif et inférieur au prix."]
    if cost_price is not None and cost_price < 0:
        errors["cost_price"] = ["Le prix d'achat ne peut pas être négatif."]
    if errors:
        raise InvalidPricing(errors)


def validate_sell_by(sell_by: date | None, *, today: date) -> None:
    if sell_by is not None and sell_by < today:
        raise SellByInPast


def normalize_options(options: Sequence[OptionInput]) -> tuple[OptionInput, ...]:
    seen: set[str] = set()
    normalized: list[OptionInput] = []
    for option in options:
        name = " ".join(option.name.split())
        values = tuple(
            dict.fromkeys(" ".join(value.split()) for value in option.values if value.strip())
        )
        if not name or not values or name.lower() in seen:
            raise InvalidVariantAttributes(
                "Chaque option doit avoir un nom unique et au moins une valeur."
            )
        seen.add(name.lower())
        normalized.append(OptionInput(name=name, values=values))
    return tuple(normalized)


def validate_attributes(
    options: Mapping[str, Sequence[str]], attributes: Mapping[str, str]
) -> dict[str, str]:
    if set(attributes) != set(options):
        raise InvalidVariantAttributes(
            f"Renseignez exactement les options : {', '.join(options) or 'aucune'}."
        )
    for name, value in attributes.items():
        if value not in options[name]:
            raise InvalidVariantAttributes(f"« {value} » n'est pas une valeur de « {name} ».")
    return {name: attributes[name] for name in options}


def variant_label(attributes: Mapping[str, str]) -> str:
    return " / ".join(attributes.values())


def discounted(price: Decimal, percent: Decimal) -> Decimal:
    return (price * (Decimal(100) - percent) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


def margin(price: Decimal, cost_price: Decimal | None) -> tuple[Decimal | None, Decimal | None]:
    if cost_price is None:
        return None, None
    amount = price - cost_price
    percent = (amount / price * 100).quantize(CENT, rounding=ROUND_HALF_UP) if price else None
    return amount, percent

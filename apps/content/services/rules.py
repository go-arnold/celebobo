from typing import Any

from apps.content.domain.errors import InvalidSchedule, SlugTaken, UnknownPaymentMethod
from apps.content.models import Banner, Page
from apps.content.repositories import ModelRepository
from apps.orders.domain.enums import PaymentMethod

PAYMENT_METHODS = frozenset(method.value for method in PaymentMethod)


class UniqueSlug:
    def __init__(self, pages: ModelRepository[Page]) -> None:
        self._pages = pages

    def __call__(self, page: Page | None, values: dict[str, Any]) -> None:
        slug = values.get("slug")
        if slug is None or (page is not None and page.slug == slug):
            return
        if self._pages.exists(slug=slug):
            raise SlugTaken


def valid_schedule(banner: Banner | None, values: dict[str, Any]) -> None:
    starts_at = values.get("starts_at", banner.starts_at if banner else None)
    ends_at = values.get("ends_at", banner.ends_at if banner else None)
    if starts_at and ends_at and ends_at <= starts_at:
        raise InvalidSchedule


def known_payment_methods(methods: list[str]) -> list[str]:
    for method in methods:
        if method not in PAYMENT_METHODS:
            raise UnknownPaymentMethod(method)
    return list(dict.fromkeys(methods))

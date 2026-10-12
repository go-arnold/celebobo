from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
from typing import Any

from apps.catalog.domain.deals import (
    AdminDeal,
    DealChanges,
    DealDraft,
    DealProduct,
    DealStatus,
    DealTerms,
)
from apps.catalog.domain.errors import InvalidDeal, ProductNotFound
from apps.catalog.models import Deal, Product
from apps.catalog.repositories import DealRepository, ProductAdminRepository
from apps.catalog.selectors import DealSelector, deal_terms
from apps.catalog.services.contracts import DealSales
from core.domain.values import provided


class LiveDeals:
    def __init__(
        self, deals: DealSelector, sales: DealSales, *, clock: Callable[[], datetime]
    ) -> None:
        self._deals = deals
        self._sales = sales
        self._clock = clock

    def by_product(
        self, product_ids: Iterable[int] | None, *, lock: bool = False
    ) -> dict[int, DealTerms]:
        now = self._clock()
        live = self._sold(self._deals.live(product_ids, now=now, lock=lock))
        return {deal.product_id: deal for deal in live if deal.status(now) is DealStatus.LIVE}

    def featured(self) -> DealTerms | None:
        return min(
            self.by_product(None).values(),
            key=lambda deal: (deal.ends_at, deal.id),
            default=None,
        )

    def _sold(self, deals: list[DealTerms]) -> list[DealTerms]:
        sold = self._sales.sold([deal.id for deal in deals]) if deals else {}
        return [replace(deal, sold=sold.get(deal.id, 0)) for deal in deals]


class DealAdminService:
    def __init__(
        self,
        deals: DealRepository,
        products: ProductAdminRepository,
        selector: DealSelector,
        sales: DealSales,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._deals = deals
        self._products = products
        self._selector = selector
        self._sales = sales
        self._clock = clock

    def page(self, status: DealStatus | None) -> list[AdminDeal]:
        deals = self._admin(self._selector.all())
        return [deal for deal in deals if status is None or deal.status is status]

    def one(self, deal_id: int) -> AdminDeal:
        return self._admin([self._selector.one(deal_id)])[0]

    def create(self, draft: DealDraft) -> Deal:
        product = self._products.get(draft.product_id, for_update=True)
        if product is None or product.is_trashed:
            raise InvalidDeal("product_id", ProductNotFound.default_detail)
        deal = Deal(
            product=product,
            variant_id=draft.variant_id,
            deal_price=draft.deal_price,
            starts_at=draft.starts_at,
            ends_at=draft.ends_at,
            quantity=draft.quantity,
            gift_label=draft.gift_label.strip(),
            is_active=draft.is_active,
        )
        self._validate(product, deal)
        deal.announced = self._status(deal).value
        return self._deals.create(
            **{field: getattr(deal, field) for field in (*_FIELDS, "product", "announced")}
        )

    def update(self, deal: Deal, changes: DealChanges) -> Deal:
        values: dict[str, Any] = dict(provided(changes))
        if "gift_label" in values:
            values["gift_label"] = values["gift_label"].strip()
        for name, value in values.items():
            setattr(deal, name, value)
        product = self._products.get(deal.product_id, for_update=True)
        if product is None:
            raise ProductNotFound
        self._validate(product, deal)
        deal.announced = self._status(deal).value
        self._deals.save(deal, fields=[*values, "announced"])
        return deal

    def delete(self, deal: Deal) -> None:
        self._deals.delete(deal)

    def tick(self) -> list[int]:
        now = self._clock()
        unsettled = self._selector.unsettled(now=now)
        sold = self._sales.sold([deal.id for deal, _ in unsettled]) if unsettled else {}
        statuses: dict[int, str] = {}
        products: list[int] = []
        for deal, announced in unsettled:
            status = replace(deal, sold=sold.get(deal.id, 0)).status(now).value
            if status != announced:
                statuses[deal.id] = status
                products.append(deal.product_id)
        self._deals.announce(statuses)
        return list(dict.fromkeys(products))

    def _validate(self, product: Product, deal: Deal) -> None:
        variants = [variant for variant in self._products.variants(product) if variant.is_active]
        if variants and deal.variant_id not in {variant.pk for variant in variants}:
            raise InvalidDeal("variant_id", "Choisissez la variante concernée par l'offre.")
        if not variants and deal.variant_id is not None:
            raise InvalidDeal("variant_id", "Ce produit n'a pas de variantes.")
        if deal.ends_at <= deal.starts_at:
            raise InvalidDeal("ends_at", "La fin de l'offre doit suivre son début.")
        regular = deal_terms(deal).regular_price
        if deal.deal_price >= regular:
            raise InvalidDeal(
                "deal_price", f"Le prix de l'offre doit être inférieur au prix normal ({regular})."
            )
        if deal.is_active and self._deals.overlaps(deal):
            raise InvalidDeal("starts_at", "Une autre offre de ce produit couvre déjà ces dates.")

    def _status(self, deal: Deal) -> DealStatus:
        terms = deal_terms(deal)
        sold = self._sales.sold([deal.pk]).get(deal.pk, 0) if deal.pk else 0
        return replace(terms, sold=sold).status(self._clock())

    def _admin(self, rows: list[tuple[DealTerms, DealProduct, str]]) -> list[AdminDeal]:
        now = self._clock()
        sold = self._sales.sold([terms.id for terms, _, _ in rows]) if rows else {}
        deals = []
        for terms, product, variant_label in rows:
            counted = replace(terms, sold=sold.get(terms.id, 0))
            deals.append(
                AdminDeal(
                    terms=counted,
                    product=product,
                    variant_label=variant_label,
                    status=counted.status(now),
                )
            )
        return deals


_FIELDS = (
    "variant_id",
    "deal_price",
    "starts_at",
    "ends_at",
    "quantity",
    "gift_label",
    "is_active",
)

from collections import defaultdict
from collections.abc import Sequence

from apps.catalog.domain.enums import StockReason
from apps.catalog.domain.errors import OutOfStock, ProductUnavailable, VariantRequired
from apps.catalog.domain.queries import StockLine, StockSource
from apps.catalog.domain.read_models import PricedLine
from apps.catalog.models import Product, ProductVariant
from apps.catalog.repositories import StockRepository


class InventoryService:
    def __init__(self, stock: StockRepository) -> None:
        self._stock = stock

    def price(self, lines: Sequence[StockLine]) -> list[PricedLine]:
        products = self._stock.for_pricing(line.product_id for line in lines)
        return [self._priced(products, line) for line in lines]

    def reserve(self, lines: Sequence[StockLine], source: StockSource) -> set[int]:
        merged = _merge(lines)
        products, variants = self._stock.lock(
            (product_id for product_id, _ in merged),
            (variant_id for _, variant_id in merged if variant_id is not None),
            visible_only=True,
        )
        with_variants = self._stock.products_with_variants(products)
        for (product_id, variant_id), quantity in merged.items():
            product = products.get(product_id)
            if product is None:
                raise ProductUnavailable(product_id)
            variant = _variant(product, variant_id, variants, required=product_id in with_variants)
            available = variant.stock if variant is not None else product.stock
            if quantity > available:
                raise OutOfStock(product_id, variant_id=variant_id, available=available)
            self._stock.move(
                product, variant, delta=-quantity, reason=StockReason.ORDER, source=source
            )
        return {product_id for product_id, _ in merged}

    def release(
        self, lines: Sequence[StockLine], source: StockSource, *, reason: StockReason, note: str
    ) -> set[int]:
        merged = _merge(lines)
        products, variants = self._stock.lock(
            (product_id for product_id, _ in merged),
            (variant_id for _, variant_id in merged if variant_id is not None),
            visible_only=False,
        )
        touched: set[int] = set()
        for (product_id, variant_id), quantity in merged.items():
            product = products.get(product_id)
            if product is None:
                continue
            variant = variants.get(variant_id) if variant_id is not None else None
            self._stock.move(
                product, variant, delta=quantity, reason=reason, source=source, note=note
            )
            touched.add(product_id)
        return touched

    @staticmethod
    def _priced(products: dict[int, Product], line: StockLine) -> PricedLine:
        product = products.get(line.product_id)
        if product is None:
            raise ProductUnavailable(line.product_id)
        options = {variant.pk: variant for variant in product.variants.all()}
        if options and line.variant_id is None:
            raise VariantRequired(line.product_id)
        variant = options.get(line.variant_id) if line.variant_id is not None else None
        if line.variant_id is not None and variant is None:
            raise ProductUnavailable(line.product_id)
        images = list(product.images.all())
        return PricedLine(
            product_id=product.pk,
            variant_id=variant.pk if variant else None,
            sku=variant.sku if variant else f"P-{product.pk}",
            name=product.name,
            variant_label=variant.label if variant else "",
            image=(variant.image if variant and variant.image else "")
            or (images[0].url if images else ""),
            unit_price=(
                variant.price if variant and variant.price is not None else product.current_price
            ),
            quantity=line.quantity,
            free_shipping=product.free_shipping,
            shipping_fee=product.shipping_fee,
        )


def _merge(lines: Sequence[StockLine]) -> dict[tuple[int, int | None], int]:
    merged: defaultdict[tuple[int, int | None], int] = defaultdict(int)
    for line in lines:
        merged[(line.product_id, line.variant_id)] += line.quantity
    return dict(sorted(merged.items(), key=lambda item: (item[0][0], item[0][1] or 0)))


def _variant(
    product: Product,
    variant_id: int | None,
    variants: dict[int, ProductVariant],
    *,
    required: bool,
) -> ProductVariant | None:
    if variant_id is None:
        if required:
            raise VariantRequired(product.pk)
        return None
    variant = variants.get(variant_id)
    if variant is None or variant.product_id != product.pk or not variant.is_active:
        raise ProductUnavailable(product.pk)
    return variant

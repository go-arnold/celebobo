from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.utils.text import slugify

from apps.catalog.domain.enums import ReviewStatus, StockReason
from apps.catalog.domain.errors import (
    BrandNameTaken,
    BrandNotFound,
    CategoryNameTaken,
    CategoryNotEmpty,
    CategoryNotFound,
    DuplicateSku,
    DuplicateVariant,
    InvalidCategoryParent,
    NegativeStock,
    ProductNotFound,
    UnknownImages,
    VariantNotFound,
    VariantsManageStock,
)
from apps.catalog.domain.management import (
    AdjustmentMode,
    BrandChanges,
    BrandDraft,
    BulkAction,
    BulkProductAction,
    CategoryChanges,
    CategoryDraft,
    OptionInput,
    ProductChanges,
    ProductDraft,
    StockAdjustment,
    VariantChanges,
    VariantDraft,
)
from apps.catalog.domain.management_rules import (
    MAX_DISCOUNT_PERCENT,
    discounted,
    normalize_options,
    validate_attributes,
    validate_pricing,
    validate_sell_by,
    variant_label,
)
from apps.catalog.domain.queries import StockSource
from apps.catalog.models import Brand, Category, Product, ProductVariant, Review, StockMovement
from apps.catalog.repositories import (
    BrandRepository,
    CategoryAdminRepository,
    ProductAdminRepository,
    ProductRepository,
    ReviewAdminRepository,
    StockRepository,
)
from apps.catalog.services.contracts import MediaUrls
from core.domain.errors import ValidationFailed
from core.domain.values import UNSET, provided

SLUG_ATTEMPTS = 50
ADMIN_SOURCE = "backoffice"
COPY_SUFFIX = " (copie)"
FORM_NOTE = "Modification depuis la fiche produit"
INVENTORY_FIELDS = ("stock", "variants")


class SlugService:
    def __init__(self, taken: Callable[[str], bool], *, max_length: int) -> None:
        self._taken = taken
        self._max_length = max_length

    def generate(self, name: str) -> str:
        base = (slugify(name) or "element")[: self._max_length - 4]
        if not self._taken(base):
            return base
        for index in range(2, SLUG_ATTEMPTS):
            candidate = f"{base}-{index}"
            if not self._taken(candidate):
                return candidate
        raise ValidationFailed(errors={"name": ["Impossible de générer un identifiant unique."]})


class ProductAdminService:
    def __init__(
        self,
        products: ProductAdminRepository,
        categories: CategoryAdminRepository,
        media: MediaUrls,
        *,
        brands: BrandRepository,
        today: Callable[[], date],
    ) -> None:
        self._products = products
        self._categories = categories
        self._brands = brands
        self._media = media
        self._today = today
        self._slugs = SlugService(products.slug_taken, max_length=280)

    def create(self, draft: ProductDraft) -> Product:
        validate_pricing(draft.price, draft.sale_price, draft.cost_price)
        validate_sell_by(draft.sell_by, today=self._today())
        category = self._category(draft.category_id)
        urls = self._image_urls(draft.image_ids)
        options = normalize_options(draft.options)
        product = self._products.create(
            name=" ".join(draft.name.split()),
            slug=self._slugs.generate(draft.name),
            description=draft.description.strip(),
            long_description=draft.long_description.strip(),
            seo_title=draft.seo_title.strip(),
            seo_description=draft.seo_description.strip(),
            category=category,
            brand=self._brand(draft.brand_id),
            badge=draft.badge.value if draft.badge else "",
            price=draft.price,
            sale_price=draft.sale_price,
            cost_price=draft.cost_price,
            care_instructions=draft.care_instructions.strip(),
            delivery_policy_primary=draft.delivery_policy_primary.strip(),
            delivery_policy_secondary=draft.delivery_policy_secondary.strip(),
            free_shipping=draft.free_shipping,
            shipping_fee=draft.shipping_fee,
            stock=0,
            stock_threshold=draft.stock_threshold,
            sell_by=draft.sell_by,
            is_active=draft.is_active,
        )
        self._products.replace_features(product, _clean_list(draft.features))
        self._products.replace_options(product, options)
        self._products.replace_images(product, urls)
        return product

    def update(self, product: Product, changes: ProductChanges) -> Product:
        values = {
            name: value for name, value in provided(changes).items() if name not in INVENTORY_FIELDS
        }
        price = values.get("price", product.price)
        sale_price = values.get("sale_price", product.sale_price)
        cost_price = values.get("cost_price", product.cost_price)
        validate_pricing(price, sale_price, cost_price)
        if "sell_by" in values:
            validate_sell_by(values["sell_by"], today=self._today())
        fields: list[str] = []
        if "category_id" in values:
            product.category = self._category(values.pop("category_id"))
            fields.append("category")
        if "brand_id" in values:
            product.brand = self._brand(values.pop("brand_id"))
            fields.append("brand")
        if "badge" in values:
            badge = values.pop("badge")
            product.badge = badge.value if badge else ""
            fields.append("badge")
        if "features" in values:
            self._products.replace_features(product, _clean_list(values.pop("features")))
        if "options" in values:
            self._products.replace_options(product, normalize_options(values.pop("options")))
        if "image_ids" in values:
            self._products.replace_images(product, self._image_urls(values.pop("image_ids")))
        for name, value in values.items():
            setattr(product, name, " ".join(value.split()) if name == "name" else value)
            fields.append(name)
        if fields:
            self._products.save(product, fields=fields)
        return product

    def trash(self, product: Product) -> None:
        self._products.soft_delete(product)

    def restore(self, product: Product) -> None:
        self._products.restore(product)

    def duplicate(self, product: Product) -> Product:
        name = f"{product.name}{COPY_SUFFIX}"
        copy = self._products.create(
            name=name,
            slug=self._slugs.generate(name),
            description=product.description,
            long_description=product.long_description,
            seo_title=product.seo_title,
            seo_description=product.seo_description,
            category=product.category,
            brand=product.brand,
            badge=product.badge,
            price=product.price,
            sale_price=product.sale_price,
            cost_price=product.cost_price,
            care_instructions=product.care_instructions,
            delivery_policy_primary=product.delivery_policy_primary,
            delivery_policy_secondary=product.delivery_policy_secondary,
            free_shipping=product.free_shipping,
            shipping_fee=product.shipping_fee,
            stock=0,
            stock_threshold=product.stock_threshold,
            sell_by=product.sell_by,
            is_active=False,
        )
        self._products.replace_features(copy, self._products.features(product))
        self._products.replace_options(
            copy,
            [
                OptionInput(name=name, values=tuple(values))
                for name, values in self._products.options(product).items()
            ],
        )
        self._products.replace_images(copy, self._products.image_urls(product))
        return copy

    def bulk(self, command: BulkProductAction) -> list[int]:
        category = (
            self._category(command.category_id)
            if command.action is BulkAction.SET_CATEGORY
            else None
        )
        if command.action is BulkAction.SET_DISCOUNT and not (
            command.percent is not None and 0 < command.percent <= MAX_DISCOUNT_PERCENT
        ):
            raise ValidationFailed(errors={"percent": ["Remise entre 1 et 90 %."]})
        return [
            product.pk
            for product in self._products.for_bulk(command.ids)
            if self._apply(product, command, category)
        ]

    def _apply(
        self, product: Product, command: BulkProductAction, category: Category | None
    ) -> bool:
        deleted = product.is_trashed
        match command.action:
            case BulkAction.ACTIVATE | BulkAction.DEACTIVATE:
                product.is_active = command.action is BulkAction.ACTIVATE
                self._products.save(product, fields=("is_active",))
            case BulkAction.TRASH if not deleted:
                self._products.soft_delete(product)
            case BulkAction.RESTORE if deleted:
                self._products.restore(product)
            case BulkAction.SET_CATEGORY if category is not None:
                product.category = category
                self._products.save(product, fields=("category",))
            case BulkAction.SET_DISCOUNT if command.percent is not None:
                product.sale_price = discounted(product.price, command.percent)
                self._products.save(product, fields=("sale_price",))
            case BulkAction.CLEAR_DISCOUNT:
                product.sale_price = None
                self._products.save(product, fields=("sale_price",))
            case _:
                return False
        return True

    def _category(self, category_id: int | None) -> Category:
        category = self._categories.get(category_id) if category_id is not None else None
        if category is None:
            raise ValidationFailed(errors={"category_id": [CategoryNotFound.default_detail]})
        return category

    def _brand(self, brand_id: int | None) -> Brand | None:
        if brand_id is None:
            return None
        brand = self._brands.get(brand_id)
        if brand is None:
            raise ValidationFailed(errors={"brand_id": [BrandNotFound.default_detail]})
        return brand

    def _image_urls(self, media_ids: Sequence[int]) -> list[str]:
        urls = self._media.product_images(media_ids)
        if set(media_ids) - set(urls):
            raise UnknownImages
        return [urls[media_id] for media_id in media_ids]


class VariantAdminService:
    def __init__(
        self, products: ProductAdminRepository, stock: StockRepository, media: MediaUrls
    ) -> None:
        self._products = products
        self._stock = stock
        self._media = media

    def add(self, product: Product, draft: VariantDraft, source: StockSource) -> ProductVariant:
        attributes = validate_attributes(self._products.options(product), draft.attributes)
        if self._products.attributes_taken(product, attributes):
            raise DuplicateVariant
        sku = (draft.sku or "").strip().upper() or self._next_sku(product)
        if self._products.sku_taken(sku):
            raise DuplicateSku
        if draft.stock < 0:
            raise NegativeStock
        if draft.price is not None:
            validate_pricing(draft.price, None, None)
        variant = self._products.create_variant(
            product,
            sku=sku,
            label=variant_label(attributes),
            attributes=attributes,
            price=draft.price,
            stock=0,
            image=self._image(draft.image_id),
            is_active=draft.is_active,
            position=len(self._products.variants(product)),
        )
        self._products.recompute_stock(product)
        if draft.stock:
            self._stock.move(
                product,
                variant,
                delta=draft.stock,
                reason=StockReason.INVENTORY,
                source=source,
                note="Stock initial",
            )
        return variant

    def update(self, variant: ProductVariant, changes: VariantChanges) -> ProductVariant:
        values = dict(provided(changes))
        product = variant.product
        fields: list[str] = []
        if "attributes" in values:
            attributes = validate_attributes(self._products.options(product), values["attributes"])
            if self._products.attributes_taken(product, attributes, exclude_id=variant.pk):
                raise DuplicateVariant
            variant.attributes = attributes
            variant.label = variant_label(attributes)
            fields += ["attributes", "label"]
        if "sku" in values:
            sku = values["sku"].strip().upper()
            if self._products.sku_taken(sku, exclude_id=variant.pk):
                raise DuplicateSku
            variant.sku = sku
            fields.append("sku")
        if "price" in values:
            if values["price"] is not None:
                validate_pricing(values["price"], None, None)
            variant.price = values["price"]
            fields.append("price")
        if "image_id" in values:
            variant.image = self._image(values["image_id"])
            fields.append("image")
        if "is_active" in values:
            variant.is_active = values["is_active"]
            fields.append("is_active")
        if fields:
            self._products.save_variant(variant, fields=fields)
            self._products.recompute_stock(product)
        return variant

    def remove(self, variant: ProductVariant) -> None:
        product = variant.product
        self._products.delete_variant(variant)
        self._products.recompute_stock(product)

    # the product form sends its whole variant list: unlisted ones go, listed ones are updated
    # (image and visibility keep their own endpoint), new ones are added
    def sync(
        self, product: Product, drafts: Sequence[VariantDraft], source: StockSource
    ) -> list[StockMovement]:
        current = {variant.pk: variant for variant in self._products.variants(product)}
        kept = {draft.id for draft in drafts if draft.id is not None}
        if kept - current.keys():
            raise VariantNotFound
        for variant_id in current.keys() - kept:
            self.remove(current[variant_id])
        movements: list[StockMovement] = []
        for draft in drafts:
            if draft.id is None:
                continue
            variant = current[draft.id]
            self.update(variant, _kept_variant_changes(variant, draft))
            if movement := self._set_stock(product, variant, draft.stock, source):
                movements.append(movement)
        for draft in drafts:
            if draft.id is None:
                self.add(product, draft, source)
        return movements

    def _set_stock(
        self, product: Product, variant: ProductVariant, level: int, source: StockSource
    ) -> StockMovement | None:
        if level == variant.stock:
            return None
        return self._stock.move(
            product,
            variant,
            delta=level - variant.stock,
            reason=StockReason.CORRECTION,
            source=source,
            note=FORM_NOTE,
        )

    def _next_sku(self, product: Product) -> str:
        index = len(self._products.variants(product)) + 1
        while self._products.sku_taken(candidate := f"CB-{product.pk}-{index}"):
            index += 1
        return candidate

    def _image(self, media_id: int | None) -> str:
        if media_id is None:
            return ""
        urls = self._media.product_images([media_id])
        if media_id not in urls:
            raise UnknownImages("image_id")
        return urls[media_id]


class StockAdjustmentService:
    def __init__(self, products: ProductAdminRepository, stock: StockRepository) -> None:
        self._products = products
        self._stock = stock

    def adjust(
        self, product: Product, command: StockAdjustment, source: StockSource
    ) -> StockMovement:
        variant = self._variant(product, command.variant_id)
        current = variant.stock if variant is not None else product.stock
        delta = command.value - current if command.mode is AdjustmentMode.SET else command.value
        if current + delta < 0:
            raise NegativeStock
        if delta == 0:
            raise ValidationFailed(errors={"value": ["Aucun changement de stock."]})
        return self._stock.move(
            product,
            variant,
            delta=delta,
            reason=command.reason,
            source=source,
            note=" ".join(command.note.split()),
        )

    def set_level(self, product: Product, level: int, source: StockSource) -> StockMovement | None:
        if level == product.stock and not self._products.has_active_variants(product):
            return None
        return self.adjust(
            product,
            StockAdjustment(
                mode=AdjustmentMode.SET, value=level, reason=StockReason.CORRECTION, note=FORM_NOTE
            ),
            source,
        )

    def _variant(self, product: Product, variant_id: int | None) -> ProductVariant | None:
        if variant_id is None:
            if self._products.has_active_variants(product):
                raise VariantsManageStock
            return None
        variant = self._products.variant(variant_id, for_update=True)
        if variant is None or variant.product_id != product.pk:
            raise VariantNotFound
        return variant


class CategoryAdminService:
    def __init__(self, categories: CategoryAdminRepository, media: MediaUrls) -> None:
        self._categories = categories
        self._media = media
        self._slugs = SlugService(categories.slug_taken, max_length=120)

    def create(self, draft: CategoryDraft) -> Category:
        name = " ".join(draft.name.split())
        if self._categories.name_taken(name):
            raise CategoryNameTaken
        return self._categories.create(
            name=name,
            slug=self._slugs.generate(name),
            description=draft.description.strip(),
            seo_title=draft.seo_title.strip(),
            seo_description=draft.seo_description.strip(),
            image=self._image(draft.image_id),
            icon=draft.icon.value,
            is_active=draft.is_active,
            position=self._categories.next_position(),
            parent=self._parent(None, draft.parent_id),
        )

    def update(self, category: Category, changes: CategoryChanges) -> Category:
        values: dict[str, Any] = dict(provided(changes))
        fields: list[str] = []
        if "name" in values:
            name = " ".join(values.pop("name").split())
            if self._categories.name_taken(name, exclude_id=category.pk):
                raise CategoryNameTaken
            category.name = name
            fields.append("name")
        if "image_id" in values:
            category.image = self._image(values.pop("image_id"))
            fields.append("image")
        if "icon" in values:
            category.icon = values.pop("icon").value
            fields.append("icon")
        if "parent_id" in values:
            category.parent = self._parent(category, values.pop("parent_id"))
            fields.append("parent")
        for name, value in values.items():
            setattr(category, name, value)
            fields.append(name)
        if fields:
            self._categories.save(category, fields=fields)
        return category

    def delete(self, category: Category, move_to: int | None) -> list[int]:
        moved: list[int] = []
        count = self._categories.products_count(category)
        if count and move_to is None:
            raise CategoryNotEmpty(count)
        if move_to is not None:
            target = self._categories.get(move_to)
            if target is None or target.pk == category.pk:
                raise ValidationFailed(errors={"move_to": [CategoryNotFound.default_detail]})
            moved = self._categories.move_products(category, target)
        self._categories.promote_children(category)
        self._categories.soft_delete(category)
        return moved

    def reorder(self, ids: Sequence[int]) -> None:
        self._categories.reorder(ids)

    def _parent(self, category: Category | None, parent_id: int | None) -> Category | None:
        if parent_id is None:
            return None
        parent = self._categories.get(parent_id)
        if parent is None or (category is not None and parent.pk == category.pk):
            raise InvalidCategoryParent(CategoryNotFound.default_detail)
        if parent.parent_id is not None:
            raise InvalidCategoryParent("Une sous-catégorie ne peut pas avoir de sous-catégories.")
        if category is not None and self._categories.has_children(category):
            raise InvalidCategoryParent("Cette catégorie a déjà des sous-catégories.")
        return parent

    def _image(self, media_id: int | None) -> str:
        if media_id is None:
            return ""
        urls = self._media.category_images([media_id])
        if media_id not in urls:
            raise UnknownImages("image_id")
        return urls[media_id]


class BrandAdminService:
    def __init__(self, brands: BrandRepository, media: MediaUrls) -> None:
        self._brands = brands
        self._media = media
        self._slugs = SlugService(brands.slug_taken, max_length=100)

    def create(self, draft: BrandDraft) -> Brand:
        name = " ".join(draft.name.split())
        if self._brands.name_taken(name):
            raise BrandNameTaken
        return self._brands.create(
            name=name,
            slug=self._slugs.generate(name),
            logo=self._logo(draft.logo_id),
            is_featured=draft.is_featured,
            is_active=draft.is_active,
            position=self._brands.next_position(),
        )

    def update(self, brand: Brand, changes: BrandChanges) -> Brand:
        values: dict[str, Any] = dict(provided(changes))
        if "name" in values:
            values["name"] = " ".join(values["name"].split())
            if self._brands.name_taken(values["name"], exclude_id=brand.pk):
                raise BrandNameTaken
        if "logo_id" in values:
            values["logo"] = self._logo(values.pop("logo_id"))
        for name, value in values.items():
            setattr(brand, name, value)
        if values:
            self._brands.save(brand, fields=list(values))
        return brand

    def _logo(self, media_id: int | None) -> str:
        if media_id is None:
            return ""
        urls = self._media.brand_logos([media_id])
        if media_id not in urls:
            raise UnknownImages("logo_id")
        return urls[media_id]


@dataclass(frozen=True, slots=True)
class Moderation:
    review: Review
    previous: ReviewStatus


class ReviewModerationService:
    def __init__(self, reviews: ReviewAdminRepository, products: ProductRepository) -> None:
        self._reviews = reviews
        self._products = products

    def moderate(self, review: Review, status: ReviewStatus) -> Moderation:
        previous = ReviewStatus(review.status)
        review.status = status.value
        self._reviews.save(review, fields=("status",))
        self._products.refresh_rating(review.product_id)
        return Moderation(review, previous)


def ensure_product(product: Product | None) -> Product:
    if product is None:
        raise ProductNotFound
    return product


def _clean_list(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(" ".join(value.split()) for value in values if value.strip()))


def _kept_variant_changes(variant: ProductVariant, draft: VariantDraft) -> VariantChanges:
    sku = (draft.sku or "").strip()
    return VariantChanges(
        attributes=draft.attributes,
        sku=sku if sku and sku.upper() != variant.sku else UNSET,
        price=draft.price,
    )

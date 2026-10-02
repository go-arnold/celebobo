from typing import Any

from rest_framework import serializers

from apps.catalog.api.v1.serializers import CategoryRefOutput, OptionOutput, ReviewAuthorOutput
from apps.catalog.domain.enums import Badge, CategoryIcon, ReviewStatus, StockReason
from apps.catalog.domain.management import (
    AdjustmentMode,
    BulkAction,
    OptionInput,
    ProductStatus,
)
from core.api.fields import MAX_INTEGER

MAX_IMAGES = 8


def _choices(enum: type[Any]) -> list[str]:
    return [item.value for item in enum]


def money(**options: Any) -> serializers.DecimalField:
    return serializers.DecimalField(max_digits=10, decimal_places=2, **options)


class OptionInputSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=60)
    values = serializers.ListField(
        child=serializers.CharField(max_length=60), allow_empty=False, max_length=30
    )

    def validate(self, attrs: dict[str, Any]) -> OptionInput:
        return OptionInput(name=attrs["name"], values=tuple(attrs["values"]))


class ProductFieldsSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(min_length=10, max_length=255)
    category_id = serializers.IntegerField(min_value=1, max_value=MAX_INTEGER)
    price = money(min_value=0)
    sale_price = money(min_value=0, allow_null=True, required=False)
    cost_price = money(min_value=0, allow_null=True, required=False)
    long_description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    badge = serializers.ChoiceField(choices=_choices(Badge), required=False, allow_null=True)
    care_instructions = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    delivery_policy_primary = serializers.CharField(
        required=False, allow_blank=True, max_length=4000
    )
    delivery_policy_secondary = serializers.CharField(
        required=False, allow_blank=True, max_length=4000
    )
    free_shipping = serializers.BooleanField(required=False)
    shipping_fee = money(min_value=0, allow_null=True, required=False)
    stock_threshold = serializers.IntegerField(min_value=0, required=False, max_value=MAX_INTEGER)
    sell_by = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    features = serializers.ListField(
        child=serializers.CharField(max_length=255), required=False, max_length=50
    )
    options = OptionInputSerializer(many=True, required=False)
    image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=MAX_INTEGER),
        required=False,
        max_length=MAX_IMAGES,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("badge"):
            attrs["badge"] = Badge(attrs["badge"])
        for name in ("features", "options", "image_ids"):
            if name in attrs:
                attrs[name] = tuple(attrs[name])
        return attrs


class ProductCreateInput(ProductFieldsSerializer):
    stock = serializers.IntegerField(min_value=0, required=False, default=0, max_value=MAX_INTEGER)


class ProductPatchInput(ProductFieldsSerializer):
    pass


class VariantInput(serializers.Serializer[Any]):
    attributes = serializers.DictField(child=serializers.CharField(max_length=60))
    sku = serializers.CharField(max_length=64, required=False, allow_null=True)
    price = money(min_value=0, allow_null=True, required=False)
    stock = serializers.IntegerField(min_value=0, required=False, default=0, max_value=MAX_INTEGER)
    image_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    is_active = serializers.BooleanField(required=False, default=True)


class VariantPatchInput(serializers.Serializer[Any]):
    attributes = serializers.DictField(child=serializers.CharField(max_length=60))
    sku = serializers.CharField(max_length=64)
    price = money(min_value=0, allow_null=True)
    image_id = serializers.IntegerField(min_value=1, allow_null=True, max_value=MAX_INTEGER)
    is_active = serializers.BooleanField()


class StockAdjustmentInput(serializers.Serializer[Any]):
    mode = serializers.ChoiceField(
        choices=_choices(AdjustmentMode), default=AdjustmentMode.DELTA.value
    )
    value = serializers.IntegerField()
    reason = serializers.ChoiceField(
        choices=[reason.value for reason in StockReason if reason.value not in ("order", "sale")]
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    variant_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["mode"] = AdjustmentMode(attrs["mode"])
        attrs["reason"] = StockReason(attrs["reason"])
        if attrs["mode"] is AdjustmentMode.SET and attrs["value"] < 0:
            raise serializers.ValidationError({"value": ["Le stock cible doit être positif."]})
        return attrs


class BulkInput(serializers.Serializer[Any]):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=MAX_INTEGER),
        allow_empty=False,
        max_length=200,
    )
    action = serializers.ChoiceField(choices=_choices(BulkAction))
    category_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    percent = serializers.DecimalField(
        max_digits=4, decimal_places=1, required=False, allow_null=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["ids"] = tuple(dict.fromkeys(attrs["ids"]))
        attrs["action"] = BulkAction(attrs["action"])
        return attrs


class AdminProductFiltersInput(serializers.Serializer[Any]):
    search = serializers.CharField(max_length=100, required=False)
    category_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    status = serializers.ChoiceField(
        choices=_choices(ProductStatus), default=ProductStatus.ACTIVE.value
    )
    on_sale = serializers.BooleanField(required=False, allow_null=True)
    out_of_stock = serializers.BooleanField(required=False, default=False)
    low_stock = serializers.BooleanField(required=False, default=False)
    badge = serializers.ChoiceField(choices=_choices(Badge), required=False)
    min_price = money(min_value=0, required=False)
    max_price = money(min_value=0, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["status"] = ProductStatus(attrs["status"])
        if "badge" in attrs:
            attrs["badge"] = Badge(attrs["badge"])
        return attrs


class CategoryFieldsSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=100)
    icon = serializers.ChoiceField(choices=_choices(CategoryIcon), required=False)
    description = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    image_id = serializers.IntegerField(
        min_value=1, required=False, allow_null=True, max_value=MAX_INTEGER
    )
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "icon" in attrs:
            attrs["icon"] = CategoryIcon(attrs["icon"])
        return attrs


class CategoryDeleteInput(serializers.Serializer[Any]):
    move_to = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)


class ReorderInput(serializers.Serializer[Any]):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=MAX_INTEGER),
        allow_empty=False,
        max_length=200,
    )


class ReviewFiltersInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=_choices(ReviewStatus), required=False)
    product_id = serializers.IntegerField(min_value=1, required=False, max_value=MAX_INTEGER)
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    search = serializers.CharField(max_length=100, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "status" in attrs:
            attrs["status"] = ReviewStatus(attrs["status"])
        return attrs


class ModerateInput(serializers.Serializer[Any]):
    status = serializers.ChoiceField(choices=_choices(ReviewStatus))


class AdminProductRowOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    category = CategoryRefOutput()
    image = serializers.CharField()
    price = money()
    sale_price = money(allow_null=True)
    cost_price = money(allow_null=True)
    current_price = money()
    margin = money(allow_null=True)
    margin_percent = serializers.DecimalField(max_digits=7, decimal_places=2, allow_null=True)
    stock = serializers.IntegerField()
    stock_threshold = serializers.IntegerField()
    low_stock = serializers.BooleanField()
    status = serializers.CharField()
    badge = serializers.CharField(allow_null=True)
    variants_count = serializers.IntegerField()
    sales_count = serializers.IntegerField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    updated_at = serializers.DateTimeField()


class AdminImageOutput(serializers.Serializer[Any]):
    url = serializers.CharField()
    position = serializers.IntegerField()


class AdminVariantOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    attributes = serializers.DictField(child=serializers.CharField())
    price = money(allow_null=True)
    stock = serializers.IntegerField()
    image = serializers.CharField()
    is_active = serializers.BooleanField()


class AdminProductDetailOutput(serializers.Serializer[Any]):
    description = serializers.CharField()
    long_description = serializers.CharField()
    care_instructions = serializers.CharField()
    delivery_policy_primary = serializers.CharField()
    delivery_policy_secondary = serializers.CharField()
    free_shipping = serializers.BooleanField()
    shipping_fee = money(allow_null=True)
    sell_by = serializers.DateField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField())
    options = OptionOutput(many=True)
    images = AdminImageOutput(many=True)
    variants = AdminVariantOutput(many=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return {**AdminProductRowOutput(instance.row).data, **super().to_representation(instance)}


class ProductStatsOutput(serializers.Serializer[Any]):
    total = serializers.IntegerField()
    active = serializers.IntegerField()
    on_sale = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    low_stock = serializers.IntegerField()
    stock_value = serializers.DecimalField(max_digits=14, decimal_places=2)
    trashed = serializers.IntegerField()


class StockMovementOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    delta = serializers.IntegerField()
    balance_after = serializers.IntegerField()
    reason = serializers.CharField()
    note = serializers.CharField()
    actor_name = serializers.CharField(allow_null=True)
    source_type = serializers.CharField()
    source_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()


class LowStockOutput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    variant_label = serializers.CharField()
    stock = serializers.IntegerField()
    threshold = serializers.IntegerField()


class AdminCategoryOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    description = serializers.CharField()
    image = serializers.CharField()
    icon = serializers.CharField()
    is_active = serializers.BooleanField()
    position = serializers.IntegerField()
    products_count = serializers.IntegerField()


class ProductRefOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()


class AdminReviewOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    product = ProductRefOutput()
    author = ReviewAuthorOutput()
    rating = serializers.IntegerField()
    message = serializers.CharField()
    status = serializers.CharField()
    verified = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class BulkOutput(serializers.Serializer[Any]):
    updated = serializers.ListField(child=serializers.IntegerField())

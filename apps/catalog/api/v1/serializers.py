from typing import Any

from rest_framework import serializers

from apps.catalog.conf import catalog_settings
from apps.catalog.domain.enums import Badge, ProductOrdering


class ProductQueryInput(serializers.Serializer[Any]):
    search = serializers.CharField(source="text", max_length=100, required=False)
    category = serializers.SlugField(max_length=120, required=False)
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    on_sale = serializers.BooleanField(required=False, allow_null=True)
    in_stock = serializers.BooleanField(required=False, allow_null=True)
    badge = serializers.ChoiceField(choices=[item.value for item in Badge], required=False)
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False
    )
    max_price = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=0, required=False
    )
    ordering = serializers.ChoiceField(
        choices=[item.value for item in ProductOrdering], required=False
    )
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        low, high = attrs.get("min_price"), attrs.get("max_price")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {"max_price": ["Le prix maximum doit être supérieur au prix minimum."]}
            )
        if "badge" in attrs:
            attrs["badge"] = Badge(attrs["badge"])
        if "ordering" in attrs:
            attrs["ordering"] = ProductOrdering(attrs["ordering"])
        if "ids" in attrs:
            attrs["ids"] = tuple(attrs["ids"])
        attrs.setdefault("page_size", catalog_settings().page_size)
        return attrs


class CategoryRefOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()


class CategoryOutput(CategoryRefOutput):
    description = serializers.CharField()
    image = serializers.CharField()
    icon = serializers.CharField()
    products_count = serializers.IntegerField()


class ProductCardOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    description = serializers.CharField()
    category = CategoryRefOutput()
    image = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    sale_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    badge = serializers.CharField(allow_null=True)
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    reviews_count = serializers.IntegerField()
    in_stock = serializers.BooleanField()
    free_shipping = serializers.BooleanField()
    is_favorite = serializers.BooleanField()


class OptionOutput(serializers.Serializer[Any]):
    name = serializers.CharField()
    values = serializers.ListField(child=serializers.CharField())


class VariantOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    attributes = serializers.DictField(child=serializers.CharField())
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    in_stock = serializers.BooleanField()
    stock = serializers.IntegerField()
    image = serializers.CharField()


class ProductDetailOutput(serializers.Serializer[Any]):
    long_description = serializers.CharField()
    images = serializers.ListField(child=serializers.CharField())
    features = serializers.ListField(child=serializers.CharField())
    care_instructions = serializers.ListField(child=serializers.CharField())
    delivery_policy_primary = serializers.CharField()
    delivery_policy_secondary = serializers.CharField()
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    low_stock = serializers.BooleanField()
    options = OptionOutput(many=True)
    variants = VariantOutput(many=True)

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return {
            **ProductCardOutput(instance.card).data,
            **super().to_representation(instance),
        }


class FacetCountOutput(serializers.Serializer[Any]):
    value = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    count = serializers.IntegerField()


class FacetsOutput(serializers.Serializer[Any]):
    categories = FacetCountOutput(many=True)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    in_stock = serializers.IntegerField()
    out_of_stock = serializers.IntegerField()
    on_sale = serializers.IntegerField()


class SuggestionOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    slug = serializers.SlugField()
    name = serializers.CharField()
    category = serializers.CharField()
    image = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class ReviewAuthorOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    name = serializers.CharField()
    avatar = serializers.CharField()


class ReviewOutput(serializers.Serializer[Any]):
    id = serializers.IntegerField()
    rating = serializers.IntegerField()
    message = serializers.CharField()
    verified = serializers.BooleanField()
    author = ReviewAuthorOutput()
    created_at = serializers.DateTimeField()


class ReviewSummaryOutput(serializers.Serializer[Any]):
    average = serializers.DecimalField(max_digits=3, decimal_places=2)
    count = serializers.IntegerField()
    distribution = serializers.DictField(child=serializers.IntegerField())


class ReviewInput(serializers.Serializer[Any]):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    message = serializers.CharField(min_length=10, max_length=2000)


class ReviewEligibilityOutput(serializers.Serializer[Any]):
    can_review = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    existing_review_id = serializers.IntegerField(allow_null=True)


class FavoriteInput(serializers.Serializer[Any]):
    product_id = serializers.IntegerField(min_value=1)

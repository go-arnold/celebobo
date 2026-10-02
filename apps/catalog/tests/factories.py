from decimal import Decimal
from typing import Any

from factory.declarations import LazyAttribute, PostGeneration, Sequence, SubFactory
from factory.django import DjangoModelFactory

from apps.catalog.models import Category, Product, ProductFeature, ProductVariant, Review


class CategoryFactory(DjangoModelFactory[Category]):
    class Meta:
        model = Category
        django_get_or_create = ("slug",)

    name = Sequence(lambda index: f"Catégorie {index}")
    slug = LazyAttribute(lambda category: category.name.lower().replace(" ", "-").replace("é", "e"))
    icon = "mobile"


def _add_image(product: Product, create: bool, extracted: str | bool | None, **_: Any) -> None:
    if create and extracted is not False:
        product.images.create(
            url=str(extracted or f"https://res.cloudinary.com/demo/{product.slug}.jpg")
        )


class ProductFactory(DjangoModelFactory[Product]):
    class Meta:
        model = Product
        skip_postgeneration_save = True

    name = Sequence(lambda index: f"Produit {index}")
    slug = LazyAttribute(lambda product: product.name.lower().replace(" ", "-"))
    description = "Un appareil fiable qui permet de rester connecté."
    category = SubFactory(CategoryFactory)
    price = Decimal("100.00")
    stock = 10
    image = PostGeneration(_add_image)


class FeatureFactory(DjangoModelFactory[ProductFeature]):
    class Meta:
        model = ProductFeature

    product = SubFactory(ProductFactory)
    name = Sequence(lambda index: f"Caractéristique {index}")


class VariantFactory(DjangoModelFactory[ProductVariant]):
    class Meta:
        model = ProductVariant

    product = SubFactory(ProductFactory)
    sku = Sequence(lambda index: f"CB-{index:05d}")
    label = "Noir / 128 Go"
    attributes = {"Couleur": "Noir", "Stockage": "128 Go"}
    stock = 3


class ReviewFactory(DjangoModelFactory[Review]):
    class Meta:
        model = Review

    product = SubFactory(ProductFactory)
    rating = 5
    message = "Très bon produit, livraison rapide."
    verified = True

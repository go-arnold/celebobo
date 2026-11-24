"""Real product photos for the demo catalogue, from Pexels (free to use, no attribution required).

Each number is a Pexels photo id: https://www.pexels.com/photo/<id>/. Without Cloudinary the seed
links the Pexels file directly; with Cloudinary it downloads the photo and uploads it there.
Every id below was checked by eye against the product or category it illustrates.
"""

from apps.demo import catalogue

PEXELS = "https://images.pexels.com/photos/{id}/pexels-photo-{id}.jpeg"

# main photo of each product: the first of its own verified photos
PRODUCTS: dict[str, int] = {
    product.name: product.photos[0] for product in catalogue.PRODUCTS if product.photos
}

CATEGORIES: dict[str, int] = {
    "mode": 35714343,
    "maison": 28726706,
    "beaute": 13516789,
    "alimentation": 16309237,
    "bebe": 8923982,
    "electromenager": 8583864,
    "sport": 30956958,
    "telephones": 3945672,
    "informatique": 19935029,
    "auto": 16451819,
}

# home banners, in the order of content.BANNERS
BANNERS: tuple[int, ...] = (18359544, 5782042, 9551373)


def photo_url(photo_id: int, *, width: int) -> str:
    return f"{PEXELS.format(id=photo_id)}?auto=compress&cs=tinysrgb&w={width}"

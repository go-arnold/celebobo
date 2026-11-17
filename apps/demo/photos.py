"""Real product photos for the demo catalogue, from Pexels (free to use, no attribution required).

Each number is a Pexels photo id: https://www.pexels.com/photo/<id>/. Without Cloudinary the seed
links the Pexels file directly; with Cloudinary it downloads the photo and uploads it there.
"""

PEXELS = "https://images.pexels.com/photos/{id}/pexels-photo-{id}.jpeg"

PRODUCTS: dict[str, int] = {
    "Samsung Galaxy A55 5G": 21854468,
    "Samsung Galaxy S24": 47261,
    "iPhone 15": 30639091,
    "Xiaomi Redmi Note 13": 14486282,
    "Tecno Spark 20 Pro": 13844013,
    "Infinix Hot 40i": 24181865,
    "Samsung Galaxy Tab A9+": 6373027,
    "iPad 10e génération": 10535365,
    "Lenovo Tab M10 Plus": 17150248,
    "HP 15s Ryzen 5": 11129922,
    "Lenovo IdeaPad Slim 3": 6611936,
    "MacBook Air M2": 3747070,
    "Dell Latitude 3540": 19935029,
    "Samsung Galaxy Buds FE": 33797659,
    "Apple AirPods (3e génération)": 3921827,
    "JBL Flip 6": 4917455,
    "Sony WH-CH720N": 7772548,
    "Samsung Galaxy Watch6": 18662969,
    "Xiaomi Smart Band 8": 374673,
    "Apple Watch SE": 5083218,
    "Chargeur rapide Samsung 25 W": 36012993,
    "Batterie externe Anker 20 000 mAh": 3921704,
    "Câble USB-C tressé 2 m": 3921711,
    "Coque silicone Galaxy A55": 1670768,
    "Manette sans fil Xbox": 30302447,
    "Nintendo Switch OLED": 4523018,
}

CATEGORIES: dict[str, int] = {
    "smartphones": 3945672,
    "tablettes": 25809251,
    "ordinateurs": 6893890,
    "audio": 210927,
    "montres": 5081914,
    "accessoires": 4072683,
    "gaming": 7887636,
}

# home banners, in the order of content.BANNERS
BANNERS: tuple[int, ...] = (9784247, 3945691, 25450654)


def photo_url(photo_id: int, *, width: int) -> str:
    return f"{PEXELS.format(id=photo_id)}?auto=compress&cs=tinysrgb&w={width}"

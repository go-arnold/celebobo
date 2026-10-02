from enum import StrEnum


class Badge(StrEnum):
    NEW = "new"
    BEST_SELLER = "best_seller"

    @property
    def label(self) -> str:
        return {"new": "Nouveauté", "best_seller": "Best-seller"}[self.value]


class CategoryIcon(StrEnum):
    MOBILE = "mobile"
    MONITOR = "monitor"
    TABLET = "tablet"
    HEADPHONE = "headphone"
    WATCH = "watch"
    GAME = "game"
    FLASH = "flash"
    CAMERA = "camera"
    PRINTER = "printer"
    KEYBOARD = "keyboard"


class ProductOrdering(StrEnum):
    RELEVANCE = "relevance"
    NEWEST = "-created_at"
    OLDEST = "created_at"
    PRICE_ASC = "price"
    PRICE_DESC = "-price"
    BEST_SELLING = "-sales"
    TOP_RATED = "-rating"
    NAME = "name"


class StockReason(StrEnum):
    INVENTORY = "inventory"
    SALE = "sale"
    ORDER = "order"
    RESTOCK = "restock"
    CORRECTION = "correction"
    LOSS = "loss"
    RETURN = "return"

    @property
    def label(self) -> str:
        return {
            "inventory": "Inventaire",
            "sale": "Vente",
            "order": "Commande",
            "restock": "Réapprovisionnement",
            "correction": "Correction",
            "loss": "Perte",
            "return": "Retour",
        }[self.value]


class ReviewStatus(StrEnum):
    PUBLISHED = "published"
    HIDDEN = "hidden"

from enum import StrEnum


class ContactSubject(StrEnum):
    ORDER = "order"
    PRODUCT = "product"
    RESELLER = "reseller"
    PARTNERSHIP = "partnership"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {
            "order": "Commande",
            "product": "Produit",
            "reseller": "Devenir revendeur",
            "partnership": "Partenariat",
            "other": "Autre",
        }[self.value]


class ContactStatus(StrEnum):
    NEW = "new"
    HANDLED = "handled"
    SPAM = "spam"


# tone of the image: a light image takes dark text, a dark image takes light text
class BannerTone(StrEnum):
    LIGHT = "light"
    DARK = "dark"

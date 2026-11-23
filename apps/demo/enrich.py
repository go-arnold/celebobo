"""A much richer demo, on top of `seed_demo`: more products, galleries of real photos, more clients
and orders, and every table the base seed leaves empty (points, store credit, cash, levels,
sanctions, Cagnotte, claims, returns, ratings, carts, favourites, consents…).

Photos are Pexels photos linked where they are (free to use, no attribution required); each id was
checked against the Pexels image server.
"""

import random
import uuid
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Consent, NotificationPreference, User
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.cagnotte.models import Campaign, Reward
from apps.cash.models import CashCollection, CashRemittance
from apps.catalog.domain.management import ProductDraft
from apps.catalog.facades import ProductAdminFacade
from apps.catalog.models import Brand, Category, Favorite, Product, ProductImage, ProductVariant
from apps.content.models import Banner, HomeSection
from apps.credit.models import CreditEntry
from apps.demo import people
from apps.demo.photos import photo_url
from apps.demo.seeder import DemoSeeder, SeedReport, quiet_side_effects
from apps.documents.domain.enums import JobFormat, JobKind
from apps.documents.facades import DocumentJobFacade, ReceiptFacade
from apps.loyalty.facades import PointsFacade
from apps.loyalty.models import LoyaltySettings
from apps.messaging.models import Conversation, Message, PriceProposal
from apps.orders.models import (
    Cart,
    CartItem,
    DeliveryAttempt,
    Order,
    OrderItem,
    OrderItemSerial,
    OrderLineReturn,
    OrderRating,
)
from apps.sales.models import DeliveryCredit, Refund, Sale
from apps.standing.models import ResellerLevel, Sanction
from apps.warranty.models import Claim
from core.api.actor import actor_from_user
from core.container import container
from core.domain.errors import DomainError

# Pexels photo ids by subject (verified on images.pexels.com)
POOLS: dict[str, tuple[int, ...]] = {
    "smartphones": (
        21854468,
        47261,
        30639091,
        14486282,
        13844013,
        24181865,
        3945672,
        6070602,
        719399,
        215582,
        4594997,
        1350462,
        214487,
        221179,
        5076516,
    ),
    "tablettes": (6373027, 10535365, 17150248, 25809251, 17767834, 7987849, 8533358),
    "ordinateurs": (
        11129922,
        6611936,
        3747070,
        19935029,
        6893890,
        16037283,
        25636747,
        17367708,
        8534385,
        18096280,
        5710687,
        36123568,
    ),
    "audio": (
        33797659,
        3921827,
        4917455,
        7772548,
        210927,
        17810098,
        3945667,
        844923,
        815494,
        12266868,
        935890,
        31683433,
        18542239,
        374606,
    ),
    "montres": (
        18662969,
        374673,
        5083218,
        5081914,
        12007330,
        15228782,
        7530583,
        9130511,
        4379289,
        5081923,
    ),
    "accessoires": (36012993, 3921704, 3921711, 1670768, 4072683, 37475677, 16814788),
    "gaming": (30302447, 4523018, 7887636, 12718842, 5961235, 12718845, 15686450),
}
PORTRAITS = (19039168, 19379640, 12455720, 18587652, 30386124, 2531355, 7657229, 4982473)
LIFESTYLE = (6331230, 3776189, 36764824, 36712920, 6331237, 36715576, 4971954, 8938735)
DELIVERY = (12203732, 6867941, 12725456, 6867965, 6867937)
BANNERS = (9784247, 3945691, 25450654)

# category slug (from the base seed) -> photo pool
CATEGORY_POOL = {
    "android": "smartphones",
    "iphone-ios": "smartphones",
    "smartphones": "smartphones",
    "tablettes": "tablettes",
    "pc-portables": "ordinateurs",
    "macbook": "ordinateurs",
    "ordinateurs-portables": "ordinateurs",
    "audio": "audio",
    "montres-connectees": "montres",
    "accessoires": "accessoires",
    "gaming": "gaming",
}

# (category slug, name, brand, price, sale price, cost, stock, description, features)
EXTRA_PRODUCTS: tuple[
    tuple[str, str, str, str, str | None, str, int, str, tuple[str, ...]], ...
] = (
    (
        "android",
        "Samsung Galaxy A15",
        "Samsung",
        "189.00",
        "169.00",
        "140.00",
        40,
        "Écran Super AMOLED 6,5\", 128 Go et batterie 5000 mAh : l'essentiel Samsung à petit prix.",
        (
            "Écran Super AMOLED 90 Hz",
            "128 Go de stockage",
            "Batterie 5000 mAh",
            "Charge rapide 25 W",
        ),
    ),
    (
        "android",
        "Samsung Galaxy A35 5G",
        "Samsung",
        "349.00",
        None,
        "275.00",
        22,
        "Le milieu de gamme Samsung en 5G : écran 120 Hz, IP67 et quatre ans de mises à jour.",
        ("5G", "Écran 120 Hz", "Étanche IP67", "Triple caméra 50 Mpx"),
    ),
    (
        "android",
        "Samsung Galaxy S23 FE",
        "Samsung",
        "549.00",
        "499.00",
        "420.00",
        12,
        "La fiche technique d'un haut de gamme à un prix plus doux, avec zoom optique x3.",
        ("Processeur Exynos 2200", "Zoom optique x3", "Recharge sans fil", "Écran 120 Hz"),
    ),
    (
        "android",
        "Xiaomi Redmi 13C",
        "Xiaomi",
        "129.00",
        None,
        "98.00",
        50,
        'Grand écran 6,74", 128 Go et triple capteur photo pour les petits budgets.',
        ('Écran 6,74" 90 Hz', "128 Go", "Batterie 5000 mAh", "Lecteur d'empreinte latéral"),
    ),
    (
        "android",
        "Xiaomi Redmi Note 13 Pro",
        "Xiaomi",
        "329.00",
        "299.00",
        "250.00",
        18,
        "Capteur 200 Mpx, écran AMOLED 1,5K et charge 67 W : la photo sans compromis.",
        ("Capteur 200 Mpx", "AMOLED 1,5K 120 Hz", "Charge 67 W", "Gorilla Glass Victus"),
    ),
    (
        "android",
        "Tecno Camon 30",
        "Tecno",
        "239.00",
        None,
        "185.00",
        26,
        "Un téléphone pensé pour les portraits, avec caméra frontale 50 Mpx et autofocus.",
        ("Selfie 50 Mpx AF", "AMOLED 120 Hz", "256 Go", "Charge 70 W"),
    ),
    (
        "android",
        "Tecno Pova 6 Pro",
        "Tecno",
        "259.00",
        "229.00",
        "195.00",
        20,
        "Batterie géante de 6000 mAh et charge rapide pour les gros utilisateurs.",
        ("Batterie 6000 mAh", "Charge 70 W", "AMOLED 120 Hz", "Lumières LED arrière"),
    ),
    (
        "android",
        "Infinix Note 40",
        "Infinix",
        "219.00",
        None,
        "170.00",
        30,
        "Charge sans fil magnétique, écran AMOLED et son JBL dans un design fin.",
        ("Charge sans fil 20 W", "Son JBL stéréo", "AMOLED 120 Hz", "256 Go"),
    ),
    (
        "android",
        "Infinix Smart 8",
        "Infinix",
        "99.00",
        "89.00",
        "72.00",
        60,
        "Le premier smartphone idéal : grand écran, 64 Go et une autonomie de deux jours.",
        ('Écran 6,6" 90 Hz', "64 Go", "Batterie 5000 mAh", "Déverrouillage facial"),
    ),
    (
        "android",
        "Google Pixel 8a",
        "Google",
        "499.00",
        None,
        "400.00",
        8,
        "Le meilleur de l'appareil photo Google et sept ans de mises à jour Android.",
        ("Puce Tensor G3", "7 ans de mises à jour", "Photo de nuit", "Étanche IP67"),
    ),
    (
        "iphone-ios",
        "iPhone 13",
        "Apple",
        "549.00",
        "519.00",
        "440.00",
        10,
        "Puce A15 Bionic, double caméra 12 Mpx et écran Super Retina XDR.",
        ("Puce A15 Bionic", "Double caméra 12 Mpx", "Face ID", "5G"),
    ),
    (
        "iphone-ios",
        "iPhone 15 Pro",
        "Apple",
        "1099.00",
        None,
        "930.00",
        5,
        "Titane, puce A17 Pro et téléobjectif x3 : l'iPhone le plus avancé.",
        ("Châssis en titane", "Puce A17 Pro", "Téléobjectif x3", "USB-C 10 Gb/s"),
    ),
    (
        "tablettes",
        "Samsung Galaxy Tab S9 FE",
        "Samsung",
        "449.00",
        "419.00",
        "350.00",
        9,
        'Écran 10,9" 90 Hz, S Pen inclus et étanchéité IP68 pour dessiner partout.',
        ("S Pen inclus", "Étanche IP68", "Écran 90 Hz", "Batterie 8000 mAh"),
    ),
    (
        "tablettes",
        "Xiaomi Pad 6",
        "Xiaomi",
        "329.00",
        None,
        "260.00",
        12,
        "Écran 2,8K 144 Hz et quatre haut-parleurs pour les films et le travail.",
        ("Écran 2,8K 144 Hz", "Snapdragon 870", "4 haut-parleurs", "Charge 33 W"),
    ),
    (
        "tablettes",
        "Lenovo Tab P12",
        "Lenovo",
        "389.00",
        "359.00",
        "300.00",
        7,
        'Grande tablette 12,7" pour la prise de notes, avec stylet et son JBL.',
        ('Écran 12,7" 3K', "Stylet inclus", "Son JBL", "Batterie 10 200 mAh"),
    ),
    (
        "pc-portables",
        "HP Pavilion 14",
        "HP",
        "649.00",
        None,
        "520.00",
        8,
        "Portable léger en aluminium, Core i5 et SSD 512 Go pour étudier et travailler.",
        ("Intel Core i5", "16 Go de RAM", "SSD 512 Go", 'Écran 14" Full HD'),
    ),
    (
        "pc-portables",
        "Lenovo ThinkPad E14",
        "Lenovo",
        "799.00",
        "749.00",
        "640.00",
        6,
        "Le portable professionnel robuste, avec clavier réputé et sécurité biométrique.",
        ("Intel Core i7", "16 Go de RAM", "SSD 512 Go", "Lecteur d'empreintes"),
    ),
    (
        "pc-portables",
        "Dell Inspiron 15",
        "Dell",
        "599.00",
        None,
        "480.00",
        10,
        'Grand écran 15,6" et pavé numérique pour la bureautique au quotidien.',
        ("Intel Core i5", "8 Go de RAM", "SSD 512 Go", "Pavé numérique"),
    ),
    (
        "pc-portables",
        "Asus VivoBook 15",
        "Asus",
        "529.00",
        "489.00",
        "410.00",
        12,
        "Un portable polyvalent et fin, écran anti-reflets et charge rapide.",
        ("AMD Ryzen 5", "8 Go de RAM", "SSD 512 Go", "Charge rapide"),
    ),
    (
        "pc-portables",
        "Acer Aspire 5",
        "Acer",
        "569.00",
        None,
        "455.00",
        9,
        'Écran IPS 15,6", Wi-Fi 6 et rétroéclairage du clavier.',
        ("Intel Core i5", "16 Go de RAM", "Wi-Fi 6", "Clavier rétroéclairé"),
    ),
    (
        "macbook",
        "MacBook Pro 14 M3",
        "Apple",
        "1799.00",
        None,
        "1500.00",
        3,
        "Puce M3, écran Liquid Retina XDR et jusqu'à 22 h d'autonomie.",
        ("Puce Apple M3", "Écran Liquid Retina XDR", "22 h d'autonomie", "Port HDMI et SD"),
    ),
    (
        "audio",
        "JBL Charge 5",
        "JBL",
        "179.00",
        "159.00",
        "130.00",
        15,
        "Enceinte étanche puissante qui recharge aussi votre téléphone.",
        ("Étanche IP67", "20 h d'autonomie", "Sert de batterie externe", "PartyBoost"),
    ),
    (
        "audio",
        "JBL Tune 520BT",
        "JBL",
        "59.00",
        None,
        "42.00",
        35,
        "Casque sans fil léger, son JBL Pure Bass et 57 h d'écoute.",
        ("57 h d'autonomie", "Pure Bass", "Pliable", "Multipoint"),
    ),
    (
        "audio",
        "Sony WF-C700N",
        "Sony",
        "119.00",
        "99.00",
        "82.00",
        18,
        "Écouteurs à réduction de bruit compacts, confortables toute la journée.",
        ("Réduction de bruit", "Étanches IPX4", "20 h avec l'étui", "Appli Sony"),
    ),
    (
        "audio",
        "Anker Soundcore Life Q30",
        "Anker",
        "89.00",
        None,
        "64.00",
        20,
        "Réduction de bruit hybride et 40 h d'écoute pour les trajets.",
        ("Réduction de bruit hybride", "40 h d'autonomie", "Charge rapide", "Égaliseur"),
    ),
    (
        "audio",
        "Marshall Emberton II",
        "Marshall",
        "169.00",
        None,
        "128.00",
        9,
        "Le son Marshall dans une enceinte de poche, 30 h d'autonomie.",
        ("Son 360°", "Étanche IP67", "30 h d'autonomie", "Design iconique"),
    ),
    (
        "montres-connectees",
        "Huawei Watch Fit 3",
        "Huawei",
        "149.00",
        "129.00",
        "105.00",
        14,
        "Grand écran AMOLED, suivi de la santé et dix jours d'autonomie.",
        ('Écran AMOLED 1,82"', "GPS intégré", "10 jours d'autonomie", "100+ sports"),
    ),
    (
        "montres-connectees",
        "Samsung Galaxy Fit3",
        "Samsung",
        "69.00",
        None,
        "48.00",
        30,
        "Bracelet connecté au grand écran, sommeil et activité suivis jour et nuit.",
        ('Écran 1,6" AMOLED', "13 jours d'autonomie", "Suivi du sommeil", "Étanche 5 ATM"),
    ),
    (
        "montres-connectees",
        "Amazfit GTR 4",
        "Amazfit",
        "179.00",
        "159.00",
        "125.00",
        11,
        "Montre ronde élégante, GPS bi-fréquence et appels Bluetooth.",
        ("GPS bi-fréquence", "Appels Bluetooth", "14 jours d'autonomie", "150 sports"),
    ),
    (
        "accessoires",
        "Chargeur Anker 65 W GaN",
        "Anker",
        "49.00",
        None,
        "32.00",
        40,
        "Un seul chargeur compact pour le portable, la tablette et le téléphone.",
        ("65 W GaN", "3 ports USB-C/A", "Compact", "Protection thermique"),
    ),
    (
        "accessoires",
        "Écouteurs filaires Samsung USB-C",
        "Samsung",
        "15.00",
        None,
        "8.00",
        80,
        "Écouteurs réglés par AKG, connecteur USB-C et micro intégré.",
        ("Son AKG", "USB-C", "Micro et télécommande", "Embouts de rechange"),
    ),
    (
        "accessoires",
        "Verre trempé Galaxy A55 (lot de 2)",
        "Samsung",
        "12.00",
        "9.00",
        "4.00",
        120,
        "Protection d'écran 9H, pose facile sans bulles.",
        ("Dureté 9H", "Lot de 2", "Pose sans bulles", "Compatible coque"),
    ),
    (
        "accessoires",
        "Support voiture magnétique",
        "Baseus",
        "19.00",
        None,
        "10.00",
        45,
        "Fixation magnétique solide pour la grille d'aération.",
        ("Aimants N52", "Rotation 360°", "Compatible MagSafe", "Installation sans outil"),
    ),
    (
        "gaming",
        "PlayStation 5 Slim",
        "Sony",
        "549.00",
        "519.00",
        "460.00",
        6,
        "La PS5 plus compacte, SSD 1 To et manette DualSense.",
        ("SSD 1 To", "4K jusqu'à 120 i/s", "Manette DualSense", "Lecteur Blu-ray"),
    ),
    (
        "gaming",
        "Manette DualSense",
        "Sony",
        "75.00",
        None,
        "55.00",
        25,
        "Retour haptique et gâchettes adaptatives pour sentir chaque partie.",
        ("Retour haptique", "Gâchettes adaptatives", "Micro intégré", "USB-C"),
    ),
    (
        "gaming",
        "Casque gaming HyperX Cloud II",
        "HyperX",
        "99.00",
        "89.00",
        "68.00",
        14,
        "Son surround 7.1 et micro antibruit pour PC et consoles.",
        ("Son 7.1", "Micro détachable", "Mousse à mémoire de forme", "Compatible PS5/PC"),
    ),
)

FIRST_NAMES = (
    "Jean",
    "Marie",
    "Didier",
    "Chantal",
    "Fiston",
    "Nadine",
    "Héritier",
    "Sandrine",
    "Blaise",
    "Prisca",
    "Junior",
    "Ornella",
    "Trésor",
    "Merveille",
    "Cédric",
    "Gloria",
    "Patient",
    "Rachel",
    "Moïse",
    "Divine",
    "Serge",
    "Pascaline",
    "Elie",
    "Bénie",
)
LAST_NAMES = (
    "Bahati",
    "Mugisho",
    "Cirhuza",
    "Bisimwa",
    "Kahindo",
    "Mapendo",
    "Zawadi",
    "Amani",
    "Bashige",
    "Furaha",
    "Nsimire",
    "Byamungu",
    "Kabuya",
    "Lumbu",
    "Shukuru",
    "Wabiwa",
)
PLACES = (
    ("Bukavu", "Ibanda"),
    ("Bukavu", "Kadutu"),
    ("Bukavu", "Bagira"),
    ("Goma", "Himbi"),
    ("Goma", "Les Volcans"),
    ("Goma", "Katindo"),
    ("Uvira", "Kalundu"),
)
# questions asked to the shop assistant: (question, answer, topic, sentiment, products shown)
QUESTIONS = (
    (
        "Un smartphone Samsung à moins de 300 $ ?",
        "Le Galaxy A35 5G (349 $) dépasse un peu ; dans votre budget, le Galaxy A15 à 169 $ ou le Galaxy A55 en promotion.",
        "smartphones",
        "positive",
        2,
    ),
    (
        "Livrez-vous à Goma ?",
        "Oui : 24 à 72 h à Goma, offerte dès 199 $ d'achat. Vous payez à la livraison par Mobile Money ou en espèces.",
        "livraison",
        "neutral",
        0,
    ),
    (
        "Quel casque pour le sport ?",
        "Les Sony WF-C700N (étanches IPX4) ou le JBL Tune 520BT, léger et 57 h d'autonomie.",
        "audio",
        "positive",
        2,
    ),
    (
        "Mon téléphone ne charge plus, que faire ?",
        "Pendant les 7 jours d'essai ou le mois de garantie, ouvrez une réclamation depuis votre commande avec une photo : réponse sous 72 h.",
        "garantie",
        "negative",
        0,
    ),
    (
        "Un portable pour un étudiant en informatique ?",
        "Le Lenovo ThinkPad E14 (Core i7, 16 Go) ou, moins cher, l'Asus VivoBook 15 avec Ryzen 5.",
        "ordinateurs",
        "positive",
        2,
    ),
    (
        "Comment utiliser mes points ?",
        "Au paiement, choisissez combien de points utiliser : 1 point = 1 $ sur le prix des articles.",
        "fidélité",
        "neutral",
        0,
    ),
    (
        "La PS5 est-elle disponible ?",
        "Oui, la PlayStation 5 Slim est en stock à 519 $ avec une manette DualSense.",
        "gaming",
        "positive",
        1,
    ),
    (
        "Pourquoi ma commande n'est pas encore arrivée ?",
        "Votre revendeur vous appelle avant de passer ; vous pouvez lui écrire depuis la discussion de la commande.",
        "commande",
        "negative",
        0,
    ),
    (
        "Quelle montre pour suivre mon sommeil ?",
        "Le Samsung Galaxy Fit3 (13 jours d'autonomie) ou la Huawei Watch Fit 3 avec GPS.",
        "montres",
        "positive",
        2,
    ),
    (
        "Puis-je payer en francs congolais ?",
        "Les prix sont en dollars ; vous pouvez afficher l'équivalent en FC et payer par Mobile Money au taux du jour.",
        "paiement",
        "neutral",
        0,
    ),
)
RATINGS = (
    (5, "Livreur ponctuel et très aimable, il a vérifié le téléphone avec moi."),
    (5, "Parfait, livré le jour même à Ibanda."),
    (4, "Bon service, un peu de retard mais il m'a prévenu."),
    (4, "Très professionnel, je recommande."),
    (3, "Correct, mais j'ai dû rappeler pour le rendez-vous."),
)


def _reseller(order: Order) -> int:
    # only orders with an assigned reseller reach here
    return int(order.assigned_reseller_id or 0)


DOUBLE_DIGIT = 9
EVERY_THIRD = 3


def _imei(rng: random.Random) -> str:
    digits = [rng.randint(0, 9) for _ in range(14)]
    total = sum(
        d if i % 2 == 0 else (d * 2 - 9 if d * 2 > DOUBLE_DIGIT else d * 2)
        for i, d in enumerate(digits)
    )
    return "".join(map(str, digits)) + str((10 - total % 10) % 10)


class DemoEnricher:
    def __init__(self, *, password: str, log: Callable[[str], None], rounds: int = 3) -> None:
        self._password = password
        self._log = log
        self._rounds = rounds
        self._rng = random.Random(4242)  # nosec B311
        self._now = timezone.now()
        self.report = SeedReport()

    def run(self) -> SeedReport:
        admin = User.objects.filter(is_superuser=True).order_by("pk").first()
        if admin is None:
            raise DomainError("Lancez d'abord seed_demo : aucun administrateur.")
        self._admin = admin
        base = DemoSeeder(
            admin_email=admin.email, password=self._password, images=False, log=self._log
        )
        base._random = random.Random(777)  # nosec B311
        base._actor = actor_from_user(admin)
        base._store = None
        with quiet_side_effects():
            self._loyalty_on()
            self._step("produits", self._extra_products)
            self._step("galeries", self._galleries)
            self._restock()
            managers = list(User.objects.filter(role="manager").order_by("pk"))
            resellers = list(User.objects.filter(role="reseller", is_active=True).order_by("pk"))
            clients = self._step("clients", lambda: self._clients(base, resellers))
            products = self._products()
            delivered: list[tuple[User, dict[str, Any]]] = []
            for round_ in range(self._rounds):
                self._log(f"  commandes, tour {round_ + 1}/{self._rounds}…")
                # resellers remit what they hold, so that new orders can be assigned to them
                staff = actor_from_user(managers[0])
                for reseller in resellers:
                    base._settle_cash(staff, reseller.pk)
                delivered += base._orders(
                    products, managers[round_ % len(managers)], resellers, clients
                )
            base._reviews(delivered)
            base._direct_sales(products, managers[0], resellers)
            for step, action in (
                ("avatars", self._avatars),
                ("bannières", self._banners),
                ("favoris et paniers", self._favorites_and_carts),
                ("consentements", self._consents),
                ("notes des livreurs", self._ratings),
                ("tentatives de livraison", self._attempts),
                ("numéros de série", self._serials),
                ("points", self._points),
                ("avoirs", self._store_credit),
                ("encaissements", self._cash),
                ("niveaux et sanctions", self._standing),
                ("Cagnotte", self._cagnotte),
                ("réclamations", self._claims),
                ("retours", self._returns),
                ("propositions de prix", self._proposals),
                ("frais de livraison", self._delivery_credits),
                ("reçus de livraison", self._receipts),
                ("exports", self._jobs),
                ("assistant", self._assistant),
            ):
                self._step(step, action)
        for name, count in base.report.counts.items():
            self.report.add(name, count)
        return self.report

    def _step(self, name: str, action: Callable[[], Any]) -> Any:
        self._log(f"  {name}…")
        return action()

    def _days_ago(self, oldest: int, newest: int) -> Any:
        return self._now - timedelta(days=self._rng.uniform(newest, oldest))

    # --- catalogue

    def _loyalty_on(self) -> None:
        LoyaltySettings.objects.update_or_create(pk=1, defaults={"points_enabled": True})

    def _extra_products(self) -> None:
        facade = container.resolve(ProductAdminFacade)
        actor = actor_from_user(self._admin)
        categories = dict(Category.objects.values_list("slug", "pk"))
        brands = dict(Brand.objects.values_list("name", "pk"))
        for slug, name, brand, price, sale, cost, stock, description, features in EXTRA_PRODUCTS:
            if Product.all_objects.filter(name=name).exists():
                continue
            if brand not in brands:
                brands[brand] = Brand.objects.create(
                    name=brand, slug=brand.lower().replace(" ", "-")
                ).pk
            facade.create(
                actor,
                ProductDraft(
                    name=name,
                    description=description,
                    long_description=description,
                    category_id=categories[slug],
                    brand_id=brands[brand],
                    price=Decimal(price),
                    sale_price=Decimal(sale) if sale else None,
                    cost_price=Decimal(cost),
                    stock=stock,
                    features=features,
                    delivery_policy_primary="Livraison en 24 à 48 h à Bukavu et à Goma",
                    delivery_policy_secondary="Retour gratuit sous 7 jours",
                ),
            )
            self.report.add("produits ajoutés")

    # every product shows 4 to 5 real photos of its kind
    def _galleries(self) -> None:
        for index, product in enumerate(Product.objects.select_related("category").order_by("pk")):
            pool = POOLS[CATEGORY_POOL.get(product.category.slug, "accessoires")]
            have = list(product.images.order_by("position").values_list("url", flat=True))
            wanted = 4 + index % 2
            start = (index * 3) % len(pool)
            position = len(have)
            for step in range(len(pool)):
                if len(have) >= wanted:
                    break
                url = photo_url(pool[(start + step) % len(pool)], width=1000)
                if url in have:
                    continue
                ProductImage.objects.create(
                    product=product, url=url, alt=product.name, position=position
                )
                have.append(url)
                position += 1
                self.report.add("photos produits")

    def _restock(self) -> None:
        Product.objects.update(stock=F("stock") + 150)
        ProductVariant.objects.update(stock=F("stock") + 60)

    def _products(self) -> list[dict[str, Any]]:
        return [
            {"id": p.pk, "slug": p.slug, "variants": list(p.variants.values_list("pk", flat=True))}
            for p in Product.objects.filter(is_active=True).prefetch_related("variants")
        ]

    # --- people and orders

    def _clients(self, base: DemoSeeder, resellers: list[User]) -> list[User]:
        clients = list(User.objects.filter(role="client").order_by("pk"))
        for index in range(36):
            first, last = (
                FIRST_NAMES[index % len(FIRST_NAMES)],
                LAST_NAMES[(index * 5) % len(LAST_NAMES)],
            )
            city, quarter = PLACES[index % len(PLACES)]
            person = people.DemoPerson(
                first, last, f"+243 99 {700 + index:03d} {1000 + index * 7:04d}", city, quarter
            )
            if User.objects.filter(
                email__iexact=people.email_for(person, "celebobo.test")
            ).exists():
                continue
            try:
                clients.append(base._client(100 + index, person, resellers))
            except DomainError as error:
                self._log(f"  client ignoré : {error.detail}")
        return clients

    def _avatars(self) -> None:
        for index, user in enumerate(User.objects.filter(avatar="").order_by("pk")):
            if user.is_superuser:
                continue
            user.avatar = photo_url(PORTRAITS[index % len(PORTRAITS)], width=300)
            user.save(update_fields=["avatar"])
            self.report.add("avatars")

    # every placement of the home page gets its pictures
    def _banners(self) -> None:
        sections = list(HomeSection.objects.select_related("category"))
        products = list(Product.objects.filter(is_active=True).order_by("-sale_price")[:12])
        plan: list[tuple[str, str, str, int, Product | None]] = [
            (
                "hero",
                "Les nouveautés Samsung sont arrivées",
                "Galaxy A, Tab et Buds",
                LIFESTYLE[0],
                None,
            ),
            (
                "hero",
                "Livraison à Bukavu en 24 h",
                "Payez à la livraison par Mobile Money",
                DELIVERY[1],
                None,
            ),
            ("hero_mini", "Écouteurs dès 15 $", "Audio", POOLS["audio"][5], None),
            ("hero_mini", "Montres connectées", "Santé et sport", POOLS["montres"][4], None),
            (
                "hero_side",
                "Portables pour étudier",
                "Rentrée",
                POOLS["ordinateurs"][5],
                products[0] if products else None,
            ),
            (
                "hero_side",
                "Gaming : PS5 et manettes",
                "Jeux",
                POOLS["gaming"][3],
                products[1] if len(products) > 1 else None,
            ),
            ("deal_side", "Chargeurs rapides", "Accessoires", POOLS["accessoires"][5], None),
            (
                "deal_side",
                "Tablettes pour toute la famille",
                "Tablettes",
                POOLS["tablettes"][4],
                None,
            ),
            ("deal_side", "Achetez depuis votre téléphone", "Simple et rapide", LIFESTYLE[2], None),
        ]
        links: dict[str, str] = {}
        for section in sections:
            slug = section.category.slug
            pool = POOLS[CATEGORY_POOL.get(slug, "accessoires")]
            title = section.title or section.category.name
            links[title] = f"/categorie/{slug}"
            plan.append(
                (
                    f"{section.kind}:{slug}",
                    title,
                    f"Le choix Celebobo en {section.category.name.lower()}",
                    pool[-1],
                    None,
                )
            )
        for position, (placement, title, subtitle, photo, product) in enumerate(plan):
            if Banner.objects.filter(placement=placement, title=title).exists():
                continue
            Banner.objects.create(
                title=title,
                subtitle=subtitle,
                image=photo_url(photo, width=1600),
                placement=placement,
                product=product,
                link_url=links.get(title, "/produits"),
                link_label="Découvrir",
                position=position,
                is_active=True,
                tone="dark",
            )
            self.report.add("bannières")

    def _favorites_and_carts(self) -> None:
        products = list(Product.objects.filter(is_active=True))
        for client in User.objects.filter(role="client"):
            for product in self._rng.sample(
                products, k=min(len(products), self._rng.randint(2, 7))
            ):
                Favorite.objects.get_or_create(user=client, product=product)
                self.report.add("favoris")
        for client in User.objects.filter(role="client").order_by("?")[:14]:
            cart, _ = Cart.objects.get_or_create(user=client)
            for product in self._rng.sample(products, k=self._rng.randint(1, 3)):
                variant = product.variants.first()
                CartItem.objects.get_or_create(
                    cart=cart,
                    product=product,
                    variant=variant,
                    defaults={"quantity": self._rng.randint(1, 2)},
                )
                self.report.add("articles en panier")
        guest = Cart.objects.create(token=uuid.uuid4())
        CartItem.objects.create(cart=guest, product=products[0], quantity=1)

    def _consents(self) -> None:
        for user in User.objects.filter(role__in=("client", "reseller")):
            for kind in ("terms", "hosting_abroad", "marketing"):
                if kind == "marketing" and user.pk % 3:
                    continue
                Consent.objects.get_or_create(
                    user=user,
                    kind=kind,
                    defaults={
                        "version": "2026-11",
                        "source": "signup",
                        "accepted_at": user.date_joined,
                    },
                )
                self.report.add("consentements")
            NotificationPreference.objects.get_or_create(
                user=user,
                defaults={
                    "preferences": {"promotions": {"email": user.pk % 2 == 0, "push": False}}
                },
            )

    # --- after the orders

    def _delivered(self) -> list[Order]:
        return list(
            Order.objects.filter(status="delivered", assigned_reseller__isnull=False).order_by("pk")
        )

    def _ratings(self) -> None:
        for index, order in enumerate(self._delivered()):
            if index % 4 == EVERY_THIRD or OrderRating.objects.filter(order=order).exists():
                continue
            score, comment = RATINGS[index % len(RATINGS)]
            OrderRating.objects.create(
                order=order,
                reseller_id=_reseller(order),
                client_id=order.client_id,
                score=score,
                comment=comment,
            )
            self.report.add("notes des livreurs")

    def _attempts(self) -> None:
        reasons = ("client_absent", "unreachable", "wrong_address")
        for index, order in enumerate(Order.objects.filter(status="shipping")[:6]):
            DeliveryAttempt.objects.create(
                order=order,
                reason=reasons[index % 3],
                note="Repasser demain matin.",
                actor_id=order.assigned_reseller_id,
                created_at=self._days_ago(3, 1),
            )
            self.report.add("tentatives de livraison")

    def _serials(self) -> None:
        items = OrderItem.objects.filter(
            order__status__in=("shipping", "delivered", "returned"),
            product__category__slug__in=(
                "android",
                "iphone-ios",
                "tablettes",
                "pc-portables",
                "macbook",
            ),
        )
        for item in items:
            OrderItem.objects.filter(pk=item.pk).update(serial_required=True)
            for _ in range(item.quantity):
                OrderItemSerial.objects.get_or_create(
                    item=item,
                    serial=_imei(self._rng),
                    defaults={"recorded_by_id": item.order.assigned_reseller_id},
                )
                self.report.add("numéros de série")

    def _points(self) -> None:
        points = container.resolve(PointsFacade)
        for order in self._delivered():
            delivered_at = (
                order.history.filter(to_status="delivered")
                .values_list("created_at", flat=True)
                .first()
                or self._now
            )
            points.delivered(order.pk, delivered_at)
            self.report.add("commandes avec points")

    def _store_credit(self) -> None:
        for index, client in enumerate(User.objects.filter(role="client").order_by("pk")[:10]):
            amount = Decimal(15 + index * 7)
            CreditEntry.objects.create(
                user=client,
                kind="issued",
                amount=amount,
                remaining=amount,
                expires_at=self._now + timedelta(days=180 - index * 9),
                note="Changement d'avis pendant l'essai",
            )
            self.report.add("avoirs")

    def _cash(self) -> None:
        managers = list(User.objects.filter(role="manager"))
        for index, order in enumerate(
            Order.objects.filter(
                status__in=("paid", "shipping", "delivered"),
                assigned_reseller__isnull=False,
                delivery_method="delivery",
            ).order_by("pk")
        ):
            if CashCollection.objects.filter(order=order).exists():
                continue
            collected = self._days_ago(20, 0)
            remitted = order.status == "delivered" and index % 5
            CashCollection.objects.create(
                reseller_id=_reseller(order),
                order=order,
                order_number=order.number,
                amount=order.total,
                covered=order.total if remitted else Decimal(0),
                collected_at=collected,
                due_at=collected + timedelta(hours=24),
            )
            self.report.add("encaissements")
            if remitted:
                CashRemittance.objects.create(
                    reseller_id=_reseller(order),
                    amount=order.total,
                    reference=f"MP-{20000 + index}",
                    received_at=collected + timedelta(hours=self._rng.randint(2, 20)),
                    recorded_by=managers[index % len(managers)],
                )
                self.report.add("reversements")

    def _standing(self) -> None:
        resellers = list(User.objects.filter(role="reseller").order_by("pk"))
        levels = (
            ("ambassadeur", "3450.00", "4.7"),
            ("confirme", "1380.00", "4.3"),
            ("debutant", "520.00", "4.1"),
            ("debutant", "160.00", None),
        )
        for reseller, (level, sales, rating) in zip(resellers, levels, strict=False):
            ResellerLevel.objects.update_or_create(
                reseller=reseller,
                defaults={
                    "level": level,
                    "sales": Decimal(sales),
                    "rating": Decimal(rating) if rating else None,
                    "reviewed_at": self._now - timedelta(days=53),
                },
            )
            self.report.add("niveaux")
        manager = User.objects.filter(role="manager").first()
        if len(resellers) > EVERY_THIRD and not Sanction.objects.exists():
            Sanction.objects.create(
                reseller=resellers[2],
                kind="warning",
                reason="Reversement de 2 commandes avec 30 heures de retard.",
                status="applied",
                created_by=manager,
                decided_by=manager,
                decided_at=self._now - timedelta(days=12),
                starts_at=self._now - timedelta(days=12),
            )
            Sanction.objects.create(
                reseller=resellers[3],
                kind="suspension",
                days=7,
                reason="Client injoignable à trois reprises sans prévenir le service.",
                status="notified",
                explain_until=self._now + timedelta(hours=30),
                explanation="J'étais en déplacement à Uvira, réseau coupé. Je m'excuse.",
                explained_at=self._now - timedelta(hours=10),
                created_by=manager,
            )
            Sanction.objects.create(
                reseller=resellers[1],
                kind="suspension",
                days=10,
                reason="Remise d'un produit sans contrôle du code de livraison.",
                status="dropped",
                decision_note="Explication acceptée, première fois.",
                decided_at=self._now - timedelta(days=30),
                created_by=manager,
                decided_by=manager,
            )
            self.report.add("sanctions", 3)

    def _cagnotte(self) -> None:
        if Campaign.objects.exists():
            return
        audio = Category.objects.filter(slug="audio").first()
        past = Campaign.objects.create(
            name="Black Friday",
            description="5 % de cashback en points sur tout le site.",
            kind="cashback",
            percent=Decimal("5"),
            starts_at=self._now - timedelta(days=60),
            ends_at=self._now - timedelta(days=50),
            payout="points",
            points_valid_days=90,
            created_by=self._admin,
        )
        running = Campaign.objects.create(
            name="Fête de l'audio",
            description="3 % de points en plus sur les écouteurs, casques et enceintes, jusqu'à 20 $ par commande.",
            kind="boosted_points",
            percent=Decimal("3"),
            starts_at=self._now - timedelta(days=3),
            ends_at=self._now + timedelta(days=11),
            cap=Decimal("20"),
            points_valid_days=60,
            created_by=self._admin,
        )
        if audio:
            running.categories.set([audio])
        Campaign.objects.create(
            name="Noël à Bukavu",
            description="10 % de remise immédiate dès 100 $ d'achat, jusqu'à 50 $.",
            kind="discount",
            percent=Decimal("10"),
            starts_at=self._now + timedelta(days=20),
            ends_at=self._now + timedelta(days=35),
            min_purchase=Decimal("100"),
            cap=Decimal("50"),
            created_by=self._admin,
        )
        self.report.add("opérations Cagnotte", 3)
        for index, order in enumerate(self._delivered()[:12]):
            amount = (order.total * Decimal("0.05")).quantize(Decimal("0.01"))
            mobile = index % 3 == 0
            status = "paid" if mobile and index % 2 == 0 else ("to_pay" if mobile else "credited")
            Order.objects.filter(pk=order.pk).update(campaign_id=past.pk, campaign_name=past.name)
            Reward.objects.create(
                campaign=past,
                order=order,
                client_id=order.client_id,
                kind="cashback",
                payout="mobile_money" if mobile else "points",
                amount=amount,
                kept=amount,
                status=status,
                available_at=self._now - timedelta(days=40),
                paid_at=self._now - timedelta(days=35) if status == "paid" else None,
                reference="MP-CB-7731" if status == "paid" else "",
            )
            self.report.add("avantages Cagnotte")

    def _claims(self) -> None:
        items = list(
            OrderItem.objects.filter(order__status="delivered").select_related("order", "product")[
                :8
            ]
        )
        manager = User.objects.filter(role="manager").first()
        plan: tuple[tuple[str, str, str, str, dict[str, Any]], ...] = (
            ("defect", "trial", "submitted", "L'écran clignote quand la luminosité est basse.", {}),
            (
                "defect",
                "warranty",
                "answered",
                "La batterie se vide en quelques heures.",
                {
                    "return_method": "shop",
                    "answer_note": "Déposez-le à la boutique avenue Mwanga, diagnostic sous 3 jours ouvrables.",
                    "answered_at": self._now - timedelta(days=2),
                },
            ),
            (
                "change_of_mind",
                "trial",
                "received",
                "Je préfère le modèle 256 Go.",
                {
                    "return_method": "reseller",
                    "answered_at": self._now - timedelta(days=4),
                    "received_at": self._now - timedelta(days=1),
                    "sealed": True,
                },
            ),
            (
                "defect",
                "warranty",
                "repairing",
                "Le haut-parleur grésille.",
                {
                    "return_method": "shop",
                    "answered_at": self._now - timedelta(days=9),
                    "received_at": self._now - timedelta(days=7),
                    "covered": True,
                    "outcome": "repair",
                    "diagnosed_at": self._now - timedelta(days=5),
                    "diagnosis_note": "Haut-parleur à remplacer, pièce commandée.",
                },
            ),
            (
                "counterfeit",
                "authenticity",
                "closed",
                "Le numéro IMEI ne correspond pas sur le site du fabricant.",
                {
                    "answered_at": self._now - timedelta(days=20),
                    "received_at": self._now - timedelta(days=18),
                    "covered": False,
                    "outcome": "not_covered",
                    "diagnosed_at": self._now - timedelta(days=16),
                    "diagnosis_note": "IMEI vérifié auprès de Samsung : authentique.",
                    "closed_at": self._now - timedelta(days=15),
                },
            ),
        )
        for item, (kind, protection, status, description, extra) in zip(items, plan, strict=False):
            if Claim.objects.filter(item=item).exists():
                continue
            pool = POOLS[
                CATEGORY_POOL.get(item.product.category.slug if item.product else "", "accessoires")
            ]
            Claim.objects.create(
                order=item.order,
                item=item,
                client_id=item.order.client_id,
                kind=kind,
                protection=protection,
                status=status,
                description=description,
                photos=[photo_url(pool[0], width=900), photo_url(pool[1], width=900)],
                answer_due=self._now + timedelta(hours=40),
                handled_by=manager if status != "submitted" else None,
                **extra,
            )
            self.report.add("réclamations")

    def _returns(self) -> None:
        item = (
            OrderItem.objects.filter(
                order__status="delivered", returned_quantity=0, amount_paid__gt=0
            )
            .order_by("-pk")
            .first()
        )
        if item is None or OrderLineReturn.objects.exists():
            return
        OrderLineReturn.objects.create(
            order=item.order,
            item=item,
            quantity=1,
            amount_paid=item.amount_paid / item.quantity,
            discount=Decimal(0),
            points=Decimal(0),
            reason="Produit défectueux à l'ouverture",
            actor=User.objects.filter(role="manager").first(),
        )
        OrderItem.objects.filter(pk=item.pk).update(returned_quantity=1)
        self.report.add("retours")
        for index, sale in enumerate(Sale.objects.filter(refunded_amount=0).order_by("-pk")[:3]):
            amount = (
                (sale.unit_price * sale.quantity / 2).quantize(Decimal("0.01"))
                if index
                else sale.unit_price
            )
            Refund.objects.create(
                sale=sale,
                kind="return" if index else "refund",
                amount=amount,
                reason="Retour en boutique",
                by=User.objects.filter(role="manager").first(),
            )
            Sale.objects.filter(pk=sale.pk).update(refunded_amount=amount)
            self.report.add("remboursements")

    def _proposals(self) -> None:
        for order in Order.objects.filter(
            status__in=("confirmed", "assigned"), assigned_reseller__isnull=False
        )[:4]:
            conversation = Conversation.objects.filter(order=order).first()
            item = order.items.first()
            if conversation is None or item is None:
                continue
            proposed = (item.unit_price * Decimal("0.95")).quantize(Decimal("1"))
            message = Message.objects.create(
                conversation=conversation,
                sender_id=order.assigned_reseller_id,
                kind="price_proposal",
                body=f"Je vous propose {proposed} $ pour {item.product_name}.",
                metadata={"proposed_price": str(proposed)},
            )
            PriceProposal.objects.create(
                conversation=conversation,
                message=message,
                subject="item_price",
                order_item=item,
                previous_price=item.unit_price,
                proposed_price=proposed,
                reason="Remise fidélité",
                status="pending",
                proposed_by_id=order.assigned_reseller_id,
            )
            self.report.add("propositions de prix")

    def _delivery_credits(self) -> None:
        for order in self._delivered():
            if order.shipping_fee <= 0 or DeliveryCredit.objects.filter(order=order).exists():
                continue
            DeliveryCredit.objects.create(
                reseller_id=_reseller(order),
                order=order,
                order_number=order.number,
                kind="credit",
                amount=order.shipping_fee,
                available_at=self._now - timedelta(days=1),
                note="Frais de livraison reversés",
            )
            self.report.add("frais de livraison reversés")

    def _receipts(self) -> None:
        receipts = container.resolve(ReceiptFacade)
        for order in self._delivered():
            try:
                receipts.delivered(order.pk)
                self.report.add("reçus de livraison")
            except Exception as error:  # noqa: BLE001 - PDF rendering depends on the container
                self._log(f"  reçu ignoré ({order.number}) : {error}")

    def _assistant(self) -> None:
        clients = list(User.objects.filter(role="client").order_by("pk")[:10])
        product_ids = list(Product.objects.filter(is_active=True).values_list("pk", flat=True))
        for index, (question, answer, topic, sentiment, shown) in enumerate(QUESTIONS):
            user = clients[index % len(clients)] if index % 3 else None
            started = self._days_ago(25, 0)
            session = AssistantSession.objects.create(
                user=user, title=question[:60], message_count=2
            )
            AssistantSession.objects.filter(pk=session.pk).update(
                created_at=started, updated_at=started
            )
            AssistantMessage.objects.create(session=session, role="user", content=question)
            AssistantMessage.objects.create(
                session=session,
                role="assistant",
                content=answer,
                product_ids=self._rng.sample(product_ids, k=shown),
                input_tokens=self._rng.randint(900, 2400),
                output_tokens=self._rng.randint(80, 260),
                cost=Decimal(self._rng.randint(4, 30)) / Decimal(10000),
                latency_ms=self._rng.randint(1400, 5200),
                sentiment=sentiment,
                topic=topic,
            )
            AssistantMessage.objects.filter(session=session).update(created_at=started)
            self.report.add("conversations assistant")

    def _jobs(self) -> None:
        jobs = container.resolve(DocumentJobFacade)
        for user, kind in (
            (self._admin, JobKind.PRODUCTS_EXPORT),
            (self._admin, JobKind.SALES_EXPORT),
        ):
            try:
                jobs.request(actor_from_user(user), kind, JobFormat.CSV, {})
                self.report.add("exports")
            except DomainError as error:
                self._log(f"  export ignoré : {error.detail}")

from apps.orders.domain.pricing import CouponKind

PAGES = (
    (
        "a-propos",
        "À propos de Celebobo",
        "Votre boutique high-tech de confiance à Kinshasa.",
        "## Notre histoire\n\nCelebobo est né à Kinshasa avec une idée simple : rendre la technologie "
        "accessible, avec des produits authentiques, des prix clairs et un vrai conseil.\n\n"
        "## Nos engagements\n\n- Des produits neufs et garantis\n- Un réseau de revendeurs partout "
        "en RDC\n- Une livraison rapide à Kinshasa\n- Un service client joignable par WhatsApp",
    ),
    (
        "guide",
        "Guide d'achat",
        "Commander en cinq étapes.",
        "1. **Choisissez** vos produits et ajoutez-les au panier.\n2. **Validez** votre adresse de "
        "livraison.\n3. **Payez** par Orange Money, M-Pesa, Airtel Money ou à la livraison.\n4. "
        "**Suivez** votre commande et échangez avec votre conseiller.\n5. **Recevez** votre colis : "
        "24 à 48 h à Kinshasa, 3 à 7 jours dans les autres villes.",
    ),
    (
        "conditions",
        "Conditions générales de vente",
        "Les règles qui encadrent vos achats.",
        "Les prix sont indiqués en dollars américains, toutes taxes comprises. Toute commande est "
        "confirmée par un conseiller. Les produits bénéficient de la garantie constructeur.",
    ),
    (
        "retours",
        "Retours et remboursements",
        "7 jours pour changer d'avis.",
        "Vous disposez de 7 jours après la livraison pour retourner un produit non utilisé dans son "
        "emballage d'origine. Le remboursement est effectué par le moyen de paiement initial.",
    ),
)

FAQ = (
    (
        "Livraison",
        "Quels sont les délais de livraison ?",
        "24 à 48 h à Kinshasa, 3 à 7 jours dans les autres villes.",
    ),
    (
        "Livraison",
        "Combien coûte la livraison ?",
        "2,98 $ à Kinshasa, offerte dès 199 $ d'achat. À partir de 7,50 $ ailleurs.",
    ),
    (
        "Paiement",
        "Quels moyens de paiement acceptez-vous ?",
        "Orange Money, M-Pesa, Airtel Money, carte bancaire et paiement à la livraison.",
    ),
    (
        "Paiement",
        "Puis-je payer à la livraison ?",
        "Oui, à Kinshasa, en espèces ou par mobile money au moment de la remise.",
    ),
    (
        "Produits",
        "Vos produits sont-ils garantis ?",
        "Oui, tous nos produits sont neufs, authentiques et couverts par la garantie constructeur.",
    ),
    (
        "Revendeurs",
        "Comment devenir revendeur ?",
        "Remplissez le formulaire « Devenir revendeur ». Notre équipe vous recontacte sous 48 h.",
    ),
)

BANNERS = (
    (
        "Galaxy A55 à prix choc",
        "Jusqu'à -30 $ cette semaine seulement",
        "/produits/samsung-galaxy-a55-5g",
        "J'en profite",
    ),
    (
        "La rentrée en toute sérénité",
        "Portables et tablettes pour étudiants",
        "/categories/ordinateurs",
        "Découvrir",
    ),
    ("Livraison offerte dès 199 $", "À Kinshasa, en 24 à 48 h", "/guide", "En savoir plus"),
)

COUPONS = (
    (
        "BIENVENUE10",
        "10 % sur la première commande (newsletter)",
        CouponKind.PERCENT,
        "10",
        "30",
        "50",
        1,
        None,
    ),
    ("RENTREE25", "25 $ dès 300 $ d'achat", CouponKind.FIXED, "25", None, "300", None, 200),
    ("KIN5", "5 $ de réduction dès 50 $ d'achat", CouponKind.FIXED, "5", None, "50", 3, None),
)

OPENING_HOURS = (
    {"days": "Lundi à vendredi", "hours": "8 h 30 à 18 h 30"},
    {"days": "Samedi", "hours": "9 h à 16 h"},
    {"days": "Dimanche", "hours": "Fermé"},
)

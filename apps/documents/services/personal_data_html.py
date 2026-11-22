"""The French, human-readable page of the personal data export, built from the JSON document."""

import re
from collections.abc import Mapping
from datetime import date, datetime
from html import escape
from typing import Any

from django.utils import timezone

from apps.accounts.domain.enums import ROLE_LABELS, AddressLabel, Availability
from apps.documents.domain.personal_data import SECTION_TITLES
from apps.orders.domain.enums import DeliveryMethod, OrderStatus, PaymentMethod
from apps.resellers.domain.enums import ApplicationStatus

FIELD_LABELS: Mapping[str, str] = {
    "id": "Identifiant",
    "email": "E-mail",
    "email_verified": "E-mail vérifié",
    "first_name": "Prénom",
    "last_name": "Nom",
    "phone_number": "Téléphone",
    "phone": "Téléphone",
    "avatar": "Photo",
    "role": "Rôle",
    "date_joined": "Inscrit le",
    "last_login": "Dernière connexion",
    "referral_code": "Code revendeur",
    "invited_by": "Invité par",
    "invited_at": "Invité le",
    "addresses": "Adresses",
    "label": "Libellé",
    "recipient": "Destinataire",
    "line1": "Adresse",
    "quarter": "Quartier",
    "city": "Ville",
    "country": "Pays",
    "is_default": "Adresse par défaut",
    "push": "Notifications push",
    "order_assigned": "Commande assignée",
    "status_changed": "Changement de statut",
    "new_message": "Nouveau message",
    "promotions": "Offres et promotions",
    "number": "Numéro",
    "status": "Statut",
    "created_at": "Créé le",
    "items": "Articles",
    "name": "Nom",
    "product": "Produit",
    "product_name": "Produit",
    "variant": "Variante",
    "sku": "Référence",
    "quantity": "Quantité",
    "unit_price": "Prix unitaire",
    "total": "Total",
    "discount": "Remise",
    "points": "Points utilisés",
    "amount_paid": "Montant payé",
    "returned_quantity": "Quantité retournée",
    "returned_amount": "Montant retourné",
    "subtotal": "Sous-total",
    "shipping_fee": "Frais de livraison",
    "coupon_code": "Code promo",
    "points_earned": "Points gagnés",
    "payment_method": "Moyen de paiement",
    "delivery": "Livraison",
    "delivery_method": "Mode",
    "address": "Adresse de livraison",
    "pickup_address": "Adresse de retrait",
    "shipping_zone": "Zone",
    "delivery_estimate": "Délai annoncé",
    "note": "Note",
    "attempts": "Tentatives de livraison",
    "reason": "Motif",
    "reseller": "Revendeur",
    "refund": "Remboursement",
    "refund_due": "Montant à rembourser",
    "refunded_at": "Remboursé le",
    "cancel_reason": "Motif d'annulation",
    "history": "Historique",
    "at": "Date",
    "by": "Par",
    "rating": "Note",
    "score": "Note",
    "comment": "Commentaire",
    "documents": "Documents",
    "invoice": "Facture",
    "delivery_receipt": "Reçu de livraison",
    "issued_at": "Émis le",
    "balance": "Solde",
    "available": "Disponible",
    "pending": "En attente",
    "next_expiry": "Expiration",
    "orders_count": "Commandes encaissées",
    "orders_total": "Total encaissé",
    "movements": "Mouvements",
    "kind": "Type",
    "amount": "Montant",
    "order_number": "Commande",
    "message": "Message",
    "verified": "Achat vérifié",
    "moderation": "Publication",
    "added_at": "Ajouté le",
    "truncated": "Liste tronquée",
    "threads": "Discussions",
    "subject": "Sujet",
    "messages": "Messages",
    "own_messages_only": "Seulement vos messages",
    "sender": "Expéditeur",
    "body": "Texte",
    "attachment": "Pièce jointe",
    "decision_note": "Motif de la décision",
    "reviewed_at": "Traitée le",
    "availability": "Disponibilité",
    "summary": "Résumé",
    "earned_total": "Commissions gagnées",
    "paid_total": "Total payé",
    "due": "Reste dû",
    "validated": "Validées",
    "delivery_fees": "Frais de livraison crédités",
    "sales": "Ventes",
    "sold_at": "Vendu le",
    "refunded_amount": "Remboursé",
    "commissions": "Commissions",
    "rule": "Règle",
    "base_amount": "Base",
    "available_at": "Disponible le",
    "statement_id": "Relevé",
    "statements": "Relevés",
    "payout_date": "Date de paiement",
    "prepared_at": "Préparé le",
    "paid_at": "Payé le",
    "lines": "Lignes",
    "payouts": "Paiements reçus",
}

VALUE_LABELS: Mapping[str, Mapping[str, str]] = {
    "status": {
        **{status.value: status.label for status in OrderStatus},
        **{status.value: status.label for status in ApplicationStatus},
        "valid": "Valide",
        "refunded": "Remboursée",
        "validated": "Validée",
        "prepared": "Préparé",
        "open": "Ouverte",
        "closed": "Fermée",
    },
    "kind": {
        "earn": "Gain",
        "spend": "Utilisation",
        "refund": "Remboursement",
        "reversal": "Annulation",
        "expiry": "Expiration",
        "referral": "Parrainage",
        "referral_reversal": "Annulation de parrainage",
        "order": "Commande",
        "support": "Service client",
        "text": "Message",
        "system": "Message automatique",
        "price_proposal": "Proposition de prix",
        "shipping_quote": "Devis de livraison",
        "earned": "Gagnée",
        "reversed": "Annulée",
        "commission": "Commission",
        "delivery_fee": "Frais de livraison",
        "delivery_fee_reversal": "Annulation de frais de livraison",
    },
    "role": {role.value: label for role, label in ROLE_LABELS.items()},
    "label": {item.value: item.label for item in AddressLabel},
    "availability": {item.value: item.label for item in Availability},
    "payment_method": {item.value: item.label for item in PaymentMethod},
    "delivery_method": {item.value: item.label for item in DeliveryMethod},
    "moderation": {"published": "Publié", "hidden": "Masqué"},
    "rule": {
        "paid": "10 % du montant payé",
        "margin": "Plafond de 50 % de la marge",
        "partner_gain": "Plafond de 20 % du gain (produit partenaire)",
        "unknown_cost": "10 % du montant payé (coût inconnu)",
        "legacy_rate": "Ancien taux",
    },
}

_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

STYLE = """
body { font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #1f2937;
  margin: 0 auto; max-width: 960px; padding: 24px 16px; line-height: 1.45; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.25rem; margin: 32px 0 8px; padding-bottom: 4px;
  border-bottom: 2px solid #e5e7eb; }
p.meta { color: #6b7280; margin: 0 0 16px; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 12px; font-size: 0.92rem; }
th, td { border: 1px solid #e5e7eb; padding: 4px 8px; text-align: left; vertical-align: top; }
th { background: #f9fafb; font-weight: 600; }
table.record > tbody > tr > th { width: 30%; }
.item { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 12px; margin: 10px 0; }
.empty { color: #9ca3af; }
nav ul { padding-left: 18px; }
"""


def render_html(document: Mapping[str, Any], *, company: Mapping[str, str]) -> str:
    sections: Mapping[str, Any] = document["data"]
    generated = _text("generated_at", document["generated_at"])
    toc = "".join(
        f'<li><a href="#{escape(key)}">{escape(_title(key))}</a></li>' for key in sections
    )
    body = "".join(
        f'<section id="{escape(key)}"><h2>{escape(_title(key))}</h2>{_block(content)}</section>'
        for key, content in sections.items()
    )
    name = escape(company.get("company_name", "Celebobo"))
    return (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Mes données — {name}</title><style>{STYLE}</style></head><body>"
        f"<h1>Mes données — {name}</h1>"
        f'<p class="meta">Export généré le {escape(generated)}. '
        "Les montants sont en dollars américains ($). Le fichier mes-donnees.json contient "
        "les mêmes informations dans un format lisible par une machine.</p>"
        f"<nav><ul>{toc}</ul></nav>{body}</body></html>"
    )


def _title(key: str) -> str:
    return SECTION_TITLES.get(key, key)


def _label(key: str) -> str:
    return FIELD_LABELS.get(key, key.replace("_", " "))


def _block(value: Any) -> str:
    if isinstance(value, Mapping):
        return _record(value)
    if isinstance(value, list):
        return _list(value)
    return f"<p>{escape(_text('', value))}</p>"


def _record(record: Mapping[str, Any]) -> str:
    if not record:
        return '<p class="empty">—</p>'
    rows = "".join(
        f"<tr><th>{escape(_label(key))}</th><td>{_cell(key, value)}</td></tr>"
        for key, value in record.items()
    )
    return f'<table class="record"><tbody>{rows}</tbody></table>'


def _list(items: list[Any]) -> str:
    if not items:
        return '<p class="empty">Aucun élément.</p>'
    if all(isinstance(item, Mapping) for item in items):
        if all(_flat(item) for item in items):
            return _grid(items)
        return "".join(f'<div class="item">{_record(item)}</div>' for item in items)
    return f"<p>{escape(', '.join(_text('', item) for item in items))}</p>"


def _grid(rows: list[Mapping[str, Any]]) -> str:
    columns: list[str] = []
    for row in rows:
        columns.extend(key for key in row if key not in columns)
    head = "".join(f"<th>{escape(_label(key))}</th>" for key in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_cell(key, row.get(key))}</td>" for key in columns) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _flat(record: Mapping[str, Any]) -> bool:
    return not any(isinstance(value, Mapping | list) for value in record.values())


def _cell(key: str, value: Any) -> str:
    if isinstance(value, Mapping | list):
        return _block(value)
    return escape(_text(key, value))


def _text(key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, str):
        if label := VALUE_LABELS.get(key, {}).get(value):
            return label
        if _INSTANT.match(value):
            return timezone.localtime(datetime.fromisoformat(value)).strftime("%d/%m/%Y %H:%M")
        if _DAY.match(value):
            return date.fromisoformat(value).strftime("%d/%m/%Y")
    return str(value)

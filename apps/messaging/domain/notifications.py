from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from apps.messaging.domain.enums import NotificationKind

ORDER_ASSIGNED_TOPIC = "order_assigned"
STATUS_CHANGED_TOPIC = "status_changed"
NEW_MESSAGE_TOPIC = "new_message"


@dataclass(frozen=True, slots=True)
class NotificationTemplate:
    title: str
    body: str
    link: str
    topic: str
    # sent by e-mail whatever the recipient's preferences (the client needs it to get the order)
    essential: bool = False


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    kind: NotificationKind
    title: str
    body: str
    link: str
    topic: str
    essential: bool = False


TEMPLATES: Mapping[NotificationKind, NotificationTemplate] = MappingProxyType(
    {
        NotificationKind.ORDER_PLACED: NotificationTemplate(
            title="Nouvelle commande {number}",
            body="Une commande de {total} $ attend d'être assignée.",
            link="/admin/commandes/{order_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.ORDER_ASSIGNED: NotificationTemplate(
            title="Commande {number} assignée",
            body="La commande {number} vous a été assignée.",
            link="/admin/commandes/{order_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.ASSIGNMENT_DECLINED: NotificationTemplate(
            title="Assignation déclinée — {number}",
            body="{reseller} a décliné la commande {number}. {reason}",
            link="/admin/commandes/{order_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.ORDER_STATUS: NotificationTemplate(
            title="Commande {number} : {status}",
            body="Votre commande {number} est maintenant « {status} ».",
            link="/compte/commandes/{number}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.NEW_MESSAGE: NotificationTemplate(
            title="Nouveau message",
            body="{sender} : {preview}",
            link="/messages/{conversation_id}",
            topic=NEW_MESSAGE_TOPIC,
        ),
        NotificationKind.SUPPORT_REQUEST: NotificationTemplate(
            title="Nouvelle discussion",
            body="{client} a ouvert une discussion : {preview}",
            link="/admin/messages/{conversation_id}",
            topic=NEW_MESSAGE_TOPIC,
        ),
        NotificationKind.CONVERSATION_ASSIGNED: NotificationTemplate(
            title="Discussion assignée",
            body="Une discussion avec {client} vous a été assignée.",
            link="/admin/messages/{conversation_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.PRICE_PROPOSED: NotificationTemplate(
            title="Nouvelle proposition de prix",
            body="{product} : {old_price} $ → {new_price} $. {reason}",
            link="/messages/{conversation_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.PRICE_ANSWERED: NotificationTemplate(
            title="Proposition {answer}",
            body="Le client a {verb} le prix de {new_price} $ pour {product}.",
            link="/admin/messages/{conversation_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.SHIPPING_QUOTED: NotificationTemplate(
            title="Frais de livraison à valider",
            body=(
                "Commande {number} : livraison à {fee} ${estimate}. "
                "Acceptez-la ou annulez sans frais."
            ),
            link="/messages/{conversation_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.SHIPPING_ANSWERED: NotificationTemplate(
            title="Frais de livraison {answer}",
            body="Le client a {verb} les frais de {fee} $ pour la commande {number}.",
            link="/admin/messages/{conversation_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.REFUND_DUE: NotificationTemplate(
            title="Remboursement à effectuer — {number}",
            body="La commande {number}, déjà payée, a été annulée : {amount} $ à rendre au client "
            "{deadline}.",
            link="/admin/commandes/{order_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.ORDER_REFUNDED: NotificationTemplate(
            title="Commande {number} remboursée",
            body="Le remboursement de {amount} $ pour votre commande {number} a été effectué.",
            link="/compte/commandes/{number}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.DELIVERY_CODE: NotificationTemplate(
            title="Votre code de livraison — {number}",
            body="Code de livraison de la commande {number} : {code}. Donnez-le au revendeur "
            "seulement quand vous avez votre commande en main et en bon état : c'est ce code "
            "qui confirme la livraison.",
            link="/compte/commandes/{number}",
            topic=STATUS_CHANGED_TOPIC,
            essential=True,
        ),
        NotificationKind.DELIVERY_CODE_LOCKED: NotificationTemplate(
            title="Code de livraison bloqué — {number}",
            body="Trop de codes incorrects pour la commande {number}. Vérifiez avec le client, "
            "puis confirmez la livraison avec un motif.",
            link="/admin/commandes/{order_id}",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.DELIVERY_ATTEMPT: NotificationTemplate(
            title="Livraison manquée — {number}",
            body="Le revendeur n'a pas pu vous livrer ({reason}). {next}",
            link="/compte/commandes/{number}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.RESELLER_RATED: NotificationTemplate(
            title="Nouvelle note : {score}/5",
            body="Le client de la commande {number} vous a donné {score}/5.",
            link="/admin/commandes/{order_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.PAYOUT_STATEMENT: NotificationTemplate(
            title="Relevé de paiement du {date}",
            body="Votre relevé du {date} est prêt : {total} $ vont vous être versés par Mobile "
            "Money. Le détail est dans vos commissions.",
            link="/admin/commissions?releve={statement_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.PAYOUT_PAID: NotificationTemplate(
            title="Paiement reçu : {amount} $",
            body="Celebobo vous a versé {amount} $ pour votre relevé du {date}.",
            link="/admin/commissions?releve={statement_id}",
            topic=STATUS_CHANGED_TOPIC,
        ),
    }
)


def render(kind: NotificationKind, **context: Any) -> RenderedNotification:
    template = TEMPLATES[kind]
    return RenderedNotification(
        kind=kind,
        title=template.title.format(**context).strip(),
        body=" ".join(template.body.format(**context).split()),
        link=template.link.format(**context),
        topic=template.topic,
        essential=template.essential,
    )


def preview(text: str, *, limit: int = 120) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"

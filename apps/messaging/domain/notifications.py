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


@dataclass(frozen=True, slots=True)
class RenderedNotification:
    kind: NotificationKind
    title: str
    body: str
    link: str
    topic: str


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
        NotificationKind.MEMBERSHIP_REQUESTED: NotificationTemplate(
            title="Abonnement Plus à confirmer",
            body="{client} a choisi la formule {plan}. Confirmez dès réception du paiement.",
            link="/admin/abonnements",
            topic=ORDER_ASSIGNED_TOPIC,
        ),
        NotificationKind.MEMBERSHIP_STARTED: NotificationTemplate(
            title="Bienvenue dans Celebobo Plus",
            body="Votre abonnement {plan} est actif jusqu'au {ends_on}.",
            link="/compte/abonnement",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.MEMBERSHIP_REJECTED: NotificationTemplate(
            title="Demande d'abonnement refusée",
            body="Votre demande d'abonnement Plus n'a pas été confirmée. {note}",
            link="/compte/abonnement",
            topic=STATUS_CHANGED_TOPIC,
        ),
        NotificationKind.MEMBERSHIP_ENDING: NotificationTemplate(
            title="Votre abonnement Plus se termine bientôt",
            body="Il prend fin le {ends_on}. Renouvelez-le pour garder la livraison offerte.",
            link="/compte/abonnement",
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
    )


def preview(text: str, *, limit: int = 120) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"

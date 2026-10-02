from collections.abc import Iterable

from django.db.models import Count, IntegerField, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce

from apps.messaging.domain.commands import ConversationFilters
from apps.messaging.domain.enums import (
    ConversationKind,
    ConversationStatus,
    MessageKind,
    NotificationKind,
)
from apps.messaging.domain.errors import ConversationNotFound
from apps.messaging.domain.read_models import (
    Audience,
    ConversationView,
    MessagePage,
    MessageView,
    NotificationView,
    ParticipantView,
    ProposalContext,
    UnreadCounts,
)
from apps.messaging.models import (
    Conversation,
    Message,
    Notification,
    Participant,
    PriceProposal,
)
from core.domain.actor import Actor


def visible_conversations(actor: Actor) -> QuerySet[Conversation]:
    conversations = Conversation.objects.all()
    if actor.is_staff:
        return conversations
    if actor.is_backoffice:
        return conversations.filter(
            Q(assigned_reseller_id=actor.user_id) | Q(client_id=actor.user_id)
        )
    if actor.user_id is not None:
        return conversations.filter(client_id=actor.user_id)
    return conversations.none()


class ConversationSelector:
    def page(
        self, actor: Actor, filters: ConversationFilters, *, offset: int, limit: int
    ) -> tuple[list[ConversationView], int]:
        conversations = self._annotated(actor, _filtered(visible_conversations(actor), filters))
        if filters.unread:
            conversations = conversations.filter(Q(unread_count__gt=0))
        page = list(
            conversations.select_related("client", "assigned_reseller", "order").order_by(
                "-last_message_at", "-pk"
            )[offset : offset + limit]
        )
        last = _last_messages(conversation.pk for conversation in page)
        return [_conversation_view(item, last.get(item.pk)) for item in page], conversations.count()

    def detail(self, actor: Actor, conversation_id: int) -> ConversationView:
        conversation = (
            self._annotated(actor, visible_conversations(actor))
            .select_related("client", "assigned_reseller", "order")
            .filter(pk=conversation_id)
            .first()
        )
        if conversation is None:
            raise ConversationNotFound
        last = _last_messages([conversation.pk])
        return _conversation_view(conversation, last.get(conversation.pk))

    def messages(
        self, actor: Actor, conversation_id: int, *, before: int | None, limit: int
    ) -> MessagePage:
        if not visible_conversations(actor).filter(pk=conversation_id).exists():
            raise ConversationNotFound
        messages = Message.objects.filter(conversation_id=conversation_id).select_related("sender")
        if before is not None:
            messages = messages.filter(pk__lt=before)
        batch = list(messages.order_by("-pk")[: limit + 1])
        has_more = len(batch) > limit
        batch = batch[:limit]
        return MessagePage(
            messages=[to_message_view(message) for message in batch],
            next_before=batch[-1].pk if has_more and batch else None,
        )

    def message(self, message_id: int) -> MessageView:
        return to_message_view(Message.objects.select_related("sender").get(pk=message_id))

    def unread_conversations(self, actor: Actor) -> int:
        return (
            self._annotated(actor, visible_conversations(actor))
            .filter(Q(unread_count__gt=0))
            .count()
        )

    def visible(self, actor: Actor, conversation_id: int) -> bool:
        return visible_conversations(actor).filter(pk=conversation_id).exists()

    def audience(self, conversation_id: int) -> Audience:
        conversation = Conversation.objects.select_related("client").get(pk=conversation_id)
        return Audience(
            conversation_id=conversation.pk,
            kind=ConversationKind(conversation.kind),
            client_id=conversation.client_id,
            client_name=_participant(conversation.client).name,
            reseller_id=conversation.assigned_reseller_id,
        )

    def first_message(self, conversation_id: int) -> MessageView:
        message = (
            Message.objects.filter(conversation_id=conversation_id)
            .exclude(kind=MessageKind.SYSTEM.value)
            .select_related("sender")
            .order_by("pk")
            .first()
        )
        if message is None:
            raise ConversationNotFound
        return to_message_view(message)

    def proposal(self, proposal_id: int) -> ProposalContext:
        proposal = PriceProposal.objects.select_related("conversation", "message").get(
            pk=proposal_id
        )
        return ProposalContext(
            conversation_id=proposal.conversation_id,
            client_id=proposal.conversation.client_id,
            proposer_id=proposal.proposed_by_id,
            product=str(proposal.message.metadata.get("product_name", "")),
            previous_price=str(proposal.previous_price),
            proposed_price=str(proposal.proposed_price),
            reason=proposal.reason,
        )

    @staticmethod
    def _annotated(actor: Actor, conversations: QuerySet[Conversation]) -> QuerySet[Conversation]:
        viewer_id = actor.user_id if actor.user_id is not None else 0
        last_read = Participant.objects.filter(
            conversation=OuterRef("pk"), user_id=viewer_id
        ).values("last_read_message_id")[:1]
        unread = (
            Message.objects.filter(conversation=OuterRef("pk"), pk__gt=OuterRef("last_read"))
            .exclude(sender_id=viewer_id)
            .exclude(kind=MessageKind.SYSTEM.value)
            .order_by()
            .values("conversation")
            .annotate(total=Count("pk"))
            .values("total")
        )
        return conversations.annotate(
            last_read=Coalesce(Subquery(last_read, output_field=IntegerField()), 0)
        ).annotate(unread_count=Coalesce(Subquery(unread, output_field=IntegerField()), 0))


class NotificationSelector:
    def page(
        self,
        recipient_id: int,
        *,
        unread_only: bool,
        kind: NotificationKind | None,
        offset: int,
        limit: int,
    ) -> tuple[list[NotificationView], int]:
        notifications = Notification.objects.filter(recipient_id=recipient_id)
        if unread_only:
            notifications = notifications.filter(is_read=False)
        if kind is not None:
            notifications = notifications.filter(kind=kind.value)
        page = notifications.order_by("-created_at", "-pk")[offset : offset + limit]
        return [_notification_view(item) for item in page], notifications.count()

    def unread(self, recipient_id: int) -> int:
        return Notification.objects.filter(recipient_id=recipient_id, is_read=False).count()

    def counts(self, actor: Actor) -> UnreadCounts:
        if actor.user_id is None:
            return UnreadCounts(notifications=0, conversations=0)
        return UnreadCounts(
            notifications=self.unread(actor.user_id),
            conversations=ConversationSelector().unread_conversations(actor),
        )


def to_message_view(message: Message) -> MessageView:
    return MessageView(
        id=message.pk,
        conversation_id=message.conversation_id,
        kind=MessageKind(message.kind),
        body=message.body,
        attachment=message.attachment,
        metadata=dict(message.metadata),
        sender=_participant(message.sender) if message.sender else None,
        client_msg_id=message.client_msg_id,
        created_at=message.created_at,
    )


def _filtered(
    conversations: QuerySet[Conversation], filters: ConversationFilters
) -> QuerySet[Conversation]:
    if filters.kind is not None:
        conversations = conversations.filter(kind=filters.kind.value)
    if filters.status is not None:
        conversations = conversations.filter(status=filters.status.value)
    if filters.search:
        term = filters.search.strip()
        conversations = conversations.filter(
            Q(subject__icontains=term)
            | Q(order__number__icontains=term)
            | Q(client__first_name__icontains=term)
            | Q(client__last_name__icontains=term)
            | Q(client__email__icontains=term)
        )
    return conversations


def _last_messages(conversation_ids: Iterable[int]) -> dict[int, Message]:
    latest = (
        Message.objects.filter(conversation_id__in=list(conversation_ids))
        .order_by("conversation_id", "-pk")
        .select_related("sender")
    )
    result: dict[int, Message] = {}
    for message in latest:
        result.setdefault(message.conversation_id, message)
    return result


def _conversation_view(conversation: Conversation, last: Message | None) -> ConversationView:
    reseller = conversation.assigned_reseller
    order = conversation.order
    return ConversationView(
        id=conversation.pk,
        kind=ConversationKind(conversation.kind),
        status=ConversationStatus(conversation.status),
        subject=conversation.subject,
        order_id=conversation.order_id,
        order_number=order.number if order else None,
        client=_participant(conversation.client),
        reseller=_participant(reseller) if reseller else None,
        last_message=to_message_view(last) if last else None,
        unread_count=getattr(conversation, "unread_count", 0),
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
    )


def _participant(user: object) -> ParticipantView:
    first = getattr(user, "first_name", "")
    last = getattr(user, "last_name", "")
    return ParticipantView(
        id=int(getattr(user, "pk", 0)),
        name=f"{first} {last}".strip() or str(getattr(user, "email", "")),
        role=str(getattr(user, "role", "client")),
        avatar=str(getattr(user, "avatar", "")),
    )


def _notification_view(notification: Notification) -> NotificationView:
    return NotificationView(
        id=notification.pk,
        kind=NotificationKind(notification.kind),
        title=notification.title,
        body=notification.body,
        link=notification.link,
        is_read=notification.is_read,
        conversation_id=notification.conversation_id,
        order_id=notification.order_id,
        created_at=notification.created_at,
    )

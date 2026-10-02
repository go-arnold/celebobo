from dataclasses import dataclass

from django.db import transaction

from apps.messaging.domain.commands import (
    ConversationFilters,
    OpenSupport,
    PostMessage,
    ProposePrice,
)
from apps.messaging.domain.enums import ConversationKind, NotificationKind
from apps.messaging.domain.errors import (
    ConversationNotFound,
    NotificationNotFound,
    ProposalNotFound,
)
from apps.messaging.domain.events import (
    ConversationAssigned,
    ConversationClosed,
    ConversationOpened,
    ConversationRead,
    ConversationReopened,
    MessagePosted,
    PriceProposalAnswered,
    PriceProposed,
)
from apps.messaging.domain.read_models import (
    ConversationView,
    MessagePage,
    MessageView,
    NotificationView,
    UnreadCounts,
)
from apps.messaging.models import Conversation
from apps.messaging.repositories import ProposalRepository
from apps.messaging.selectors import (
    ConversationSelector,
    NotificationSelector,
    visible_conversations,
)
from apps.messaging.services.contracts import Directory
from apps.messaging.services.conversations import ConversationService
from apps.messaging.services.notifications import InboxService, NotificationFanout
from apps.messaging.services.proposals import ProposalService
from apps.orders.domain.errors import ResellerNotFound
from apps.orders.domain.events import (
    AssignmentDeclined,
    OrderAssigned,
    OrderPlaced,
    OrderStatusChanged,
)
from core.domain.actor import Actor
from core.domain.errors import Unauthenticated
from core.events.contracts import EventPublisher
from core.observability.decorators import logged_facade


@dataclass(frozen=True, slots=True)
class ConversationPage:
    conversations: list[ConversationView]
    total: int


@dataclass(frozen=True, slots=True)
class NotificationPage:
    notifications: list[NotificationView]
    total: int
    unread: int


@logged_facade
class ConversationFacade:
    def __init__(
        self,
        *,
        conversations: ConversationService,
        selector: ConversationSelector,
        directory: Directory,
        publisher: EventPublisher,
    ) -> None:
        self._conversations = conversations
        self._selector = selector
        self._directory = directory
        self._publisher = publisher

    def page(
        self, actor: Actor, filters: ConversationFilters, *, offset: int, limit: int
    ) -> ConversationPage:
        conversations, total = self._selector.page(actor, filters, offset=offset, limit=limit)
        return ConversationPage(conversations, total)

    def detail(self, actor: Actor, conversation_id: int) -> ConversationView:
        return self._selector.detail(actor, conversation_id)

    def messages(
        self, actor: Actor, conversation_id: int, *, before: int | None, limit: int
    ) -> MessagePage:
        return self._selector.messages(actor, conversation_id, before=before, limit=limit)

    def open_support(self, actor: Actor, command: OpenSupport) -> ConversationView:
        client_id = _user_id(actor)
        with transaction.atomic():
            conversation, message = self._conversations.open_support(client_id, command)
            self._publisher.publish(
                ConversationOpened(
                    conversation_id=conversation.pk,
                    kind=ConversationKind(conversation.kind),
                    client_id=client_id,
                    actor_id=client_id,
                )
            )
            self._published(message.pk, conversation.pk, client_id)
        return self._selector.detail(actor, conversation.pk)

    def post(self, actor: Actor, conversation_id: int, command: PostMessage) -> MessageView:
        sender_id = _user_id(actor)
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            message, created = self._conversations.post(actor, conversation, command)
            if created:
                self._published(message.pk, conversation.pk, sender_id)
        return self._selector.message(message.pk)

    def read(self, actor: Actor, conversation_id: int, message_id: int | None) -> int:
        user_id = _user_id(actor)
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            read_up_to = self._conversations.mark_read(actor, conversation, message_id)
            self._publisher.publish(
                ConversationRead(
                    conversation_id=conversation.pk,
                    user_id=user_id,
                    message_id=read_up_to,
                    actor_id=user_id,
                )
            )
        return read_up_to

    def close(self, actor: Actor, conversation_id: int) -> ConversationView:
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            if self._conversations.close(conversation, note="Discussion clôturée."):
                self._publisher.publish(
                    ConversationClosed(conversation_id=conversation.pk, actor_id=actor.user_id)
                )
        return self._selector.detail(actor, conversation_id)

    def reopen(self, actor: Actor, conversation_id: int) -> ConversationView:
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            if self._conversations.reopen(conversation):
                self._publisher.publish(
                    ConversationReopened(conversation_id=conversation.pk, actor_id=actor.user_id)
                )
        return self._selector.detail(actor, conversation_id)

    def assign(self, actor: Actor, conversation_id: int, reseller_id: int) -> ConversationView:
        name = self._directory.reseller_name(reseller_id)
        if name is None:
            raise ResellerNotFound
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            self._conversations.assign(conversation, reseller_id, name)
            self._publisher.publish(
                ConversationAssigned(
                    conversation_id=conversation.pk,
                    reseller_id=reseller_id,
                    actor_id=actor.user_id,
                )
            )
        return self._selector.detail(actor, conversation_id)

    def _published(self, message_id: int, conversation_id: int, sender_id: int | None) -> None:
        self._publisher.publish(
            MessagePosted(
                conversation_id=conversation_id,
                message_id=message_id,
                sender_id=sender_id,
                actor_id=sender_id,
            )
        )


@logged_facade
class ProposalFacade:
    def __init__(
        self,
        *,
        proposals: ProposalService,
        repository: ProposalRepository,
        selector: ConversationSelector,
        publisher: EventPublisher,
    ) -> None:
        self._proposals = proposals
        self._repository = repository
        self._selector = selector
        self._publisher = publisher

    def propose(self, actor: Actor, conversation_id: int, command: ProposePrice) -> MessageView:
        with transaction.atomic():
            conversation = _locked(actor, conversation_id)
            proposal = self._proposals.propose(actor, conversation, command)
            self._publisher.publish(
                PriceProposed(
                    conversation_id=conversation.pk,
                    proposal_id=proposal.pk,
                    order_id=conversation.order_id,
                    item_id=proposal.order_item_id,
                    previous_price=proposal.previous_price,
                    price=proposal.proposed_price,
                    actor_id=actor.user_id,
                )
            )
            self._publisher.publish(
                MessagePosted(
                    conversation_id=conversation.pk,
                    message_id=proposal.message_id,
                    sender_id=actor.user_id,
                    actor_id=actor.user_id,
                )
            )
        return self._selector.message(proposal.message_id)

    def respond(self, actor: Actor, proposal_id: int, *, accept: bool) -> MessageView:
        with transaction.atomic():
            proposal = self._repository.get(proposal_id, for_update=True)
            if proposal is None or not self._selector.visible(actor, proposal.conversation_id):
                raise ProposalNotFound
            self._proposals.respond(actor, proposal, accept=accept)
            self._publisher.publish(
                PriceProposalAnswered(
                    conversation_id=proposal.conversation_id,
                    proposal_id=proposal.pk,
                    accepted=accept,
                    actor_id=actor.user_id,
                )
            )
        return self._selector.message(proposal.message_id)


@logged_facade
class NotificationFacade:
    def __init__(self, *, inbox: InboxService, selector: NotificationSelector) -> None:
        self._inbox = inbox
        self._selector = selector

    def page(
        self,
        actor: Actor,
        *,
        unread_only: bool,
        kind: NotificationKind | None,
        offset: int,
        limit: int,
    ) -> NotificationPage:
        user_id = _user_id(actor)
        notifications, total = self._selector.page(
            user_id, unread_only=unread_only, kind=kind, offset=offset, limit=limit
        )
        return NotificationPage(notifications, total, self._selector.unread(user_id))

    def counts(self, actor: Actor) -> UnreadCounts:
        return self._selector.counts(actor)

    def read(self, actor: Actor, notification_id: int) -> None:
        if not self._inbox.mark_read(_user_id(actor), notification_id):
            raise NotificationNotFound

    def read_all(self, actor: Actor) -> int:
        return self._inbox.mark_all_read(_user_id(actor))


def _locked(actor: Actor, conversation_id: int) -> Conversation:
    conversation = (
        visible_conversations(actor)
        .select_for_update(of=("self",))
        .filter(pk=conversation_id)
        .first()
    )
    if conversation is None:
        raise ConversationNotFound
    return conversation


def _user_id(actor: Actor) -> int:
    if actor.user_id is None:
        raise Unauthenticated
    return actor.user_id


@logged_facade
class NotificationRouter:
    def __init__(
        self,
        *,
        fanout: NotificationFanout,
        selector: ConversationSelector,
        directory: Directory,
    ) -> None:
        self._fanout = fanout
        self._selector = selector
        self._directory = directory

    def order_placed(self, event: OrderPlaced) -> None:
        self._fanout.order_placed(event.order_id)

    def order_assigned(self, event: OrderAssigned) -> None:
        self._fanout.order_assigned(event.order_id, event.reseller_id)

    def assignment_declined(self, event: AssignmentDeclined) -> None:
        self._fanout.assignment_declined(event.order_id, event.reseller_id, event.reason)

    def order_status_changed(self, event: OrderStatusChanged) -> None:
        self._fanout.order_status_changed(event.order_id, event.status, event.actor_id)

    def message_posted(self, event: MessagePosted) -> None:
        if event.sender_id is None:
            return
        audience = self._selector.audience(event.conversation_id)
        message = self._selector.message(event.message_id)
        recipients = [audience.client_id]
        if audience.reseller_id is not None:
            recipients.append(audience.reseller_id)
        elif event.sender_id == audience.client_id and audience.kind is ConversationKind.SUPPORT:
            recipients.extend(self._directory.staff_ids())
        self._fanout.message_posted(
            conversation_id=event.conversation_id,
            participant_ids=recipients,
            sender_id=event.sender_id,
            sender_name=message.sender.name if message.sender else "Celebobo",
            body=message.body,
        )

    def support_opened(self, event: ConversationOpened) -> None:
        if event.kind is not ConversationKind.SUPPORT:
            return
        audience = self._selector.audience(event.conversation_id)
        first = self._selector.first_message(event.conversation_id)
        self._fanout.support_opened(
            conversation_id=event.conversation_id, client_name=audience.client_name, body=first.body
        )

    def conversation_assigned(self, event: ConversationAssigned) -> None:
        audience = self._selector.audience(event.conversation_id)
        self._fanout.conversation_assigned(
            conversation_id=event.conversation_id,
            reseller_id=event.reseller_id,
            client_name=audience.client_name,
        )

    def price_proposed(self, event: PriceProposed) -> None:
        context = self._selector.proposal(event.proposal_id)
        self._fanout.price_proposed(
            conversation_id=context.conversation_id,
            client_id=context.client_id,
            product=context.product,
            old_price=context.previous_price,
            new_price=context.proposed_price,
            reason=context.reason,
        )

    def price_answered(self, event: PriceProposalAnswered) -> None:
        context = self._selector.proposal(event.proposal_id)
        self._fanout.price_answered(
            conversation_id=context.conversation_id,
            proposer_id=context.proposer_id,
            product=context.product,
            new_price=context.proposed_price,
            accepted=event.accepted,
        )

from collections.abc import Callable
from datetime import datetime

from apps.messaging.domain.commands import ProposePrice
from apps.messaging.domain.enums import ConversationKind, MessageKind, ProposalStatus
from apps.messaging.domain.errors import (
    ConversationClosedError,
    NotAnOrderConversation,
    ProposalAlreadyAnswered,
)
from apps.messaging.models import Conversation, PriceProposal
from apps.messaging.repositories import MessageRepository, ProposalRepository
from apps.messaging.services.contracts import OrderGateway
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.errors import InvalidProposedPrice
from core.domain.actor import Actor
from core.domain.errors import Forbidden


class ProposalService:
    def __init__(
        self,
        proposals: ProposalRepository,
        messages: MessageRepository,
        conversations: ConversationService,
        orders: OrderGateway,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._proposals = proposals
        self._messages = messages
        self._conversations = conversations
        self._orders = orders
        self._clock = clock

    def propose(
        self, actor: Actor, conversation: Conversation, command: ProposePrice
    ) -> PriceProposal:
        if conversation.kind != ConversationKind.ORDER.value or conversation.order_id is None:
            raise NotAnOrderConversation
        if not conversation.is_open:
            raise ConversationClosedError
        item = self._orders.adjustable(actor, conversation.order_id, command.item_id)
        if command.new_price <= 0 or command.new_price > item.list_unit_price:
            raise InvalidProposedPrice
        self._proposals.supersede_pending(conversation, item.item_id)
        reason = " ".join(command.reason.split())
        message = self._messages.create(
            conversation,
            sender_id=actor.user_id,
            kind=MessageKind.PRICE_PROPOSAL.value,
            body=reason,
            metadata={
                "order_id": item.order_id,
                "item_id": item.item_id,
                "product_name": item.name,
                "quantity": item.quantity,
                "previous_price": str(item.unit_price),
                "proposed_price": str(command.new_price),
                "reason": reason,
                "status": ProposalStatus.PENDING.value,
            },
        )
        proposal = self._proposals.create(
            conversation=conversation,
            message=message,
            order_item_id=item.item_id,
            previous_price=item.unit_price,
            proposed_price=command.new_price,
            reason=reason,
            proposed_by_id=actor.user_id,
        )
        message.metadata = {**message.metadata, "proposal_id": proposal.pk}
        message.save(update_fields=["metadata"])
        return proposal

    def respond(self, actor: Actor, proposal: PriceProposal, *, accept: bool) -> PriceProposal:
        conversation = proposal.conversation
        if not actor.owns(conversation.client_id):
            raise Forbidden
        if proposal.status != ProposalStatus.PENDING.value:
            raise ProposalAlreadyAnswered
        if not conversation.is_open:
            raise ConversationClosedError
        if accept and conversation.order_id is not None:
            self._orders.apply_price(
                actor, conversation.order_id, proposal.order_item_id, proposal.proposed_price
            )
        status = ProposalStatus.ACCEPTED if accept else ProposalStatus.REFUSED
        self._proposals.answer(proposal, status, self._clock())
        verb = "acceptée" if accept else "refusée"
        self._conversations.system_message(
            conversation,
            f"Proposition {verb} : {proposal.previous_price} $ → {proposal.proposed_price} $.",
            {"event": "proposal_answered", "proposal_id": proposal.pk, "status": status.value},
        )
        return proposal

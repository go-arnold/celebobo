from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from apps.messaging.domain.commands import ProposePrice, QuoteShipping
from apps.messaging.domain.enums import (
    ConversationKind,
    MessageKind,
    ProposalStatus,
    ProposalSubject,
)
from apps.messaging.domain.errors import (
    ConversationClosedError,
    NotAnOrderConversation,
    ProposalAlreadyAnswered,
)
from apps.messaging.models import Conversation, PriceProposal
from apps.messaging.repositories import MessageRepository, ProposalRepository
from apps.messaging.services.contracts import OrderGateway
from apps.messaging.services.conversations import ConversationService
from apps.orders.domain.errors import InvalidProposedPrice, InvalidShippingQuote
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
        order_id = self._ensure_order_thread(conversation)
        item = self._orders.adjustable(actor, order_id, command.item_id)
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

    def quote_shipping(
        self, actor: Actor, conversation: Conversation, command: QuoteShipping
    ) -> PriceProposal:
        order_id = self._ensure_order_thread(conversation)
        order = self._orders.shipping_quotable(actor, order_id)
        if command.fee < 0:
            raise InvalidShippingQuote
        self._proposals.supersede_pending(conversation, None)
        reason = " ".join(command.reason.split())
        estimate = " ".join(command.delivery_estimate.split()) or order.delivery_estimate
        message = self._messages.create(
            conversation,
            sender_id=actor.user_id,
            kind=MessageKind.SHIPPING_QUOTE.value,
            body=reason,
            metadata={
                "order_id": order.order_id,
                "order_number": order.order_number,
                "city": order.city,
                "proposed_fee": str(command.fee),
                "delivery_estimate": estimate,
                "reason": reason,
                "status": ProposalStatus.PENDING.value,
            },
        )
        proposal = self._proposals.create(
            conversation=conversation,
            message=message,
            subject=ProposalSubject.SHIPPING.value,
            previous_price=Decimal(0),
            proposed_price=command.fee,
            delivery_estimate=estimate,
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
        shipping = proposal.subject == ProposalSubject.SHIPPING
        if accept and conversation.order_id is not None:
            if shipping:
                self._orders.accept_shipping(
                    actor,
                    conversation.order_id,
                    proposal.proposed_price,
                    proposal.delivery_estimate,
                )
            elif proposal.order_item_id is not None:
                self._orders.apply_price(
                    actor, conversation.order_id, proposal.order_item_id, proposal.proposed_price
                )
        status = ProposalStatus.ACCEPTED if accept else ProposalStatus.REFUSED
        self._proposals.answer(proposal, status, self._clock())
        self._conversations.system_message(
            conversation,
            _answer_text(proposal, accept=accept),
            {"event": "proposal_answered", "proposal_id": proposal.pk, "status": status.value},
        )
        return proposal

    @staticmethod
    def _ensure_order_thread(conversation: Conversation) -> int:
        if conversation.kind != ConversationKind.ORDER.value or conversation.order_id is None:
            raise NotAnOrderConversation
        if not conversation.is_open:
            raise ConversationClosedError
        return conversation.order_id


def _answer_text(proposal: PriceProposal, *, accept: bool) -> str:
    if proposal.subject == ProposalSubject.SHIPPING:
        verb = "acceptés" if accept else "refusés"
        estimate = f" ({proposal.delivery_estimate})" if proposal.delivery_estimate else ""
        return f"Frais de livraison {verb} : {proposal.proposed_price} ${estimate}."
    verb = "acceptée" if accept else "refusée"
    return f"Proposition {verb} : {proposal.previous_price} $ → {proposal.proposed_price} $."

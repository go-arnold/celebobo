from core.domain.errors import BusinessRuleViolation, Conflict, NotFound, ValidationFailed


class ConversationNotFound(NotFound):
    default_code = "conversation_not_found"
    default_detail = "Discussion introuvable."


class ConversationClosedError(BusinessRuleViolation):
    default_code = "conversation_closed"
    default_detail = "Cette discussion est clôturée."


class EmptyMessage(ValidationFailed):
    default_code = "empty_message"
    default_detail = "Le message est vide."

    def __init__(self) -> None:
        super().__init__(errors={"body": [self.default_detail]})


class NotAnOrderConversation(BusinessRuleViolation):
    default_code = "not_an_order_conversation"
    default_detail = "Les propositions de prix se font dans la discussion d'une commande."


class NotASupportConversation(BusinessRuleViolation):
    default_code = "not_a_support_conversation"
    default_detail = "Seules les discussions d'assistance peuvent être assignées."


class ProposalNotFound(NotFound):
    default_code = "proposal_not_found"
    default_detail = "Proposition introuvable."


class ProposalAlreadyAnswered(Conflict):
    default_code = "proposal_already_answered"
    default_detail = "Cette proposition a déjà reçu une réponse."


class NotificationNotFound(NotFound):
    default_code = "notification_not_found"
    default_detail = "Notification introuvable."

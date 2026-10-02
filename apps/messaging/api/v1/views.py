from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.messaging.api.v1.serializers import (
    AssignConversationInput,
    ConversationFiltersInput,
    ConversationOutput,
    MessageOutput,
    MessageQueryInput,
    NotificationOutput,
    NotificationQueryInput,
    OpenSupportInput,
    PostMessageInput,
    ProposePriceInput,
    ReadAllOutput,
    ReadInput,
    ReadOutput,
    RespondProposalInput,
    UnreadCountsOutput,
)
from apps.messaging.domain.commands import (
    ConversationFilters,
    OpenSupport,
    PostMessage,
    ProposePrice,
)
from apps.messaging.domain.enums import NotificationKind
from apps.messaging.facades import ConversationFacade, NotificationFacade, ProposalFacade
from apps.messaging.permissions import (
    CONVERSATIONS_ASSIGN,
    CONVERSATIONS_MODERATE,
    CONVERSATIONS_OPEN_SUPPORT,
    CONVERSATIONS_RESPOND_PROPOSAL,
    CONVERSATIONS_USE,
    NOTIFICATIONS_VIEW,
    PRICE_ADJUST,
)
from core.api.pagination import page_of, page_request, page_response
from core.api.views import UseCaseViewSet
from core.container import Inject


class ConversationViewSet(UseCaseViewSet):
    action_permissions = {
        "list": (CONVERSATIONS_USE,),
        "create": (CONVERSATIONS_OPEN_SUPPORT,),
        "retrieve": (CONVERSATIONS_USE,),
        "messages": (CONVERSATIONS_USE,),
        "post": (CONVERSATIONS_USE,),
        "read": (CONVERSATIONS_USE,),
        "close": (CONVERSATIONS_MODERATE,),
        "reopen": (CONVERSATIONS_MODERATE,),
        "assign": (CONVERSATIONS_ASSIGN,),
    }
    conversations = Inject(ConversationFacade)

    @extend_schema(parameters=[ConversationFiltersInput], responses=page_of(ConversationOutput))
    def list(self, request: Request) -> Response:
        filters = self.parse(
            ConversationFiltersInput, into=ConversationFilters, data=request.query_params
        )
        page = page_request(request, default_size=20, max_size=50)
        result = self.conversations.page(
            self.actor, filters, offset=page.offset, limit=page.page_size
        )
        return page_response(
            request,
            page,
            total=result.total,
            results=ConversationOutput(result.conversations, many=True).data,
        )

    @extend_schema(request=OpenSupportInput, responses={201: ConversationOutput})
    def create(self, request: Request) -> Response:
        command = self.parse(OpenSupportInput, into=OpenSupport)
        return self.respond(
            ConversationOutput, self.conversations.open_support(self.actor, command), status=201
        )

    @extend_schema(responses=ConversationOutput)
    def retrieve(self, request: Request, conversation_id: int) -> Response:
        return self.respond(
            ConversationOutput, self.conversations.detail(self.actor, conversation_id)
        )

    @extend_schema(parameters=[MessageQueryInput], responses=MessageOutput(many=True))
    def messages(self, request: Request, conversation_id: int) -> Response:
        query = self.validated(MessageQueryInput, data=request.query_params)
        page = self.conversations.messages(
            self.actor, conversation_id, before=query.get("before"), limit=query["limit"]
        )
        return Response(
            {
                "results": MessageOutput(page.messages, many=True).data,
                "meta": {"next_before": page.next_before},
            }
        )

    @extend_schema(request=PostMessageInput, responses={201: MessageOutput})
    def post(self, request: Request, conversation_id: int) -> Response:
        command = self.parse(PostMessageInput, into=PostMessage)
        message = self.conversations.post(self.actor, conversation_id, command)
        return self.respond(MessageOutput, message, status=201)

    @extend_schema(request=ReadInput, responses=ReadOutput)
    def read(self, request: Request, conversation_id: int) -> Response:
        last = self.validated(ReadInput).get("last_message_id")
        read_up_to = self.conversations.read(self.actor, conversation_id, last)
        return Response({"last_read_message_id": read_up_to})

    @extend_schema(request=None, responses=ConversationOutput)
    def close(self, request: Request, conversation_id: int) -> Response:
        return self.respond(
            ConversationOutput, self.conversations.close(self.actor, conversation_id)
        )

    @extend_schema(request=None, responses=ConversationOutput)
    def reopen(self, request: Request, conversation_id: int) -> Response:
        return self.respond(
            ConversationOutput, self.conversations.reopen(self.actor, conversation_id)
        )

    @extend_schema(request=AssignConversationInput, responses=ConversationOutput)
    def assign(self, request: Request, conversation_id: int) -> Response:
        reseller_id = self.validated(AssignConversationInput)["reseller_id"]
        return self.respond(
            ConversationOutput,
            self.conversations.assign(self.actor, conversation_id, reseller_id),
        )


class ProposalViewSet(UseCaseViewSet):
    action_permissions = {
        "create": (PRICE_ADJUST,),
        "respond": (CONVERSATIONS_RESPOND_PROPOSAL,),
    }
    proposals = Inject(ProposalFacade)

    @extend_schema(request=ProposePriceInput, responses={201: MessageOutput})
    def create(self, request: Request, conversation_id: int) -> Response:
        command = self.parse(ProposePriceInput, into=ProposePrice)
        message = self.proposals.propose(self.actor, conversation_id, command)
        return self.respond(MessageOutput, message, status=201)

    @extend_schema(request=RespondProposalInput, responses=MessageOutput)
    def respond_to(self, request: Request, proposal_id: int) -> Response:
        accept = self.validated(RespondProposalInput)["accept"]
        return self.respond(
            MessageOutput, self.proposals.respond(self.actor, proposal_id, accept=accept)
        )


class NotificationViewSet(UseCaseViewSet):
    action_permissions = dict.fromkeys(
        ("list", "counts", "read", "read_all"), (NOTIFICATIONS_VIEW,)
    )
    notifications = Inject(NotificationFacade)

    @extend_schema(parameters=[NotificationQueryInput], responses=page_of(NotificationOutput))
    def list(self, request: Request) -> Response:
        query = self.validated(NotificationQueryInput, data=request.query_params)
        page = page_request(request, default_size=20, max_size=100)
        result = self.notifications.page(
            self.actor,
            unread_only=query["unread"],
            kind=NotificationKind(query["kind"]) if query.get("kind") else None,
            offset=page.offset,
            limit=page.page_size,
        )
        return page_response(
            request,
            page,
            total=result.total,
            results=NotificationOutput(result.notifications, many=True).data,
            meta={"unread": result.unread},
        )

    @extend_schema(responses=UnreadCountsOutput)
    def counts(self, request: Request) -> Response:
        return self.respond(UnreadCountsOutput, self.notifications.counts(self.actor))

    @extend_schema(request=None, responses={204: None})
    def read(self, request: Request, notification_id: int) -> Response:
        self.notifications.read(self.actor, notification_id)
        return Response(status=204)

    @extend_schema(request=None, responses=ReadAllOutput)
    def read_all(self, request: Request) -> Response:
        return Response({"updated": self.notifications.read_all(self.actor)})

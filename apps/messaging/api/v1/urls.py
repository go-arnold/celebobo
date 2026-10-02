from django.urls import path

from apps.messaging.api.v1.views import ConversationViewSet, NotificationViewSet, ProposalViewSet

urlpatterns = [
    path(
        "conversations/",
        ConversationViewSet.as_view({"get": "list", "post": "create"}),
        name="conversations",
    ),
    path(
        "conversations/<id:conversation_id>/",
        ConversationViewSet.as_view({"get": "retrieve"}),
        name="conversation",
    ),
    path(
        "conversations/<id:conversation_id>/messages/",
        ConversationViewSet.as_view({"get": "messages", "post": "post"}),
        name="conversation-messages",
    ),
    path(
        "conversations/<id:conversation_id>/read/",
        ConversationViewSet.as_view({"post": "read"}),
        name="conversation-read",
    ),
    path(
        "conversations/<id:conversation_id>/close/",
        ConversationViewSet.as_view({"post": "close"}),
        name="conversation-close",
    ),
    path(
        "conversations/<id:conversation_id>/reopen/",
        ConversationViewSet.as_view({"post": "reopen"}),
        name="conversation-reopen",
    ),
    path(
        "conversations/<id:conversation_id>/assign/",
        ConversationViewSet.as_view({"post": "assign"}),
        name="conversation-assign",
    ),
    path(
        "conversations/<id:conversation_id>/price-proposals/",
        ProposalViewSet.as_view({"post": "create"}),
        name="price-proposals",
    ),
    path(
        "price-proposals/<id:proposal_id>/respond/",
        ProposalViewSet.as_view({"post": "respond_to"}),
        name="price-proposal-respond",
    ),
    path("notifications/", NotificationViewSet.as_view({"get": "list"}), name="notifications"),
    path(
        "notifications/unread-counts/",
        NotificationViewSet.as_view({"get": "counts"}),
        name="notification-counts",
    ),
    path(
        "notifications/read-all/",
        NotificationViewSet.as_view({"post": "read_all"}),
        name="notifications-read-all",
    ),
    path(
        "notifications/<id:notification_id>/read/",
        NotificationViewSet.as_view({"post": "read"}),
        name="notification-read",
    ),
]

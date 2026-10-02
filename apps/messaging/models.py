from django.conf import settings
from django.db import models

from apps.messaging.domain.enums import (
    ConversationKind,
    ConversationStatus,
    MessageKind,
    NotificationKind,
    ProposalStatus,
)

KIND_CHOICES = [(item.value, item.value) for item in ConversationKind]
STATUS_CHOICES = [(item.value, item.value) for item in ConversationStatus]
MESSAGE_KIND_CHOICES = [(item.value, item.value) for item in MessageKind]
PROPOSAL_STATUS_CHOICES = [(item.value, item.value) for item in ProposalStatus]
NOTIFICATION_KIND_CHOICES = [(item.value, item.value) for item in NotificationKind]


class Conversation(models.Model):
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    status = models.CharField(
        max_length=8, choices=STATUS_CHOICES, default=ConversationStatus.OPEN.value
    )
    subject = models.CharField(max_length=160, blank=True)
    order = models.OneToOneField(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conversation",
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversations"
    )
    assigned_reseller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_conversations",
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "discussion"
        verbose_name_plural = "discussions"
        ordering = ("-last_message_at", "-pk")
        indexes = (
            models.Index(fields=("client", "-last_message_at"), name="messaging_conv_client"),
            models.Index(
                fields=("assigned_reseller", "-last_message_at"), name="messaging_conv_reseller"
            ),
        )

    def __str__(self) -> str:
        return self.subject or f"Discussion {self.pk}"

    @property
    def is_open(self) -> bool:
        return self.status == ConversationStatus.OPEN.value


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    kind = models.CharField(
        max_length=16, choices=MESSAGE_KIND_CHOICES, default=MessageKind.TEXT.value
    )
    body = models.TextField(max_length=4000, blank=True)
    attachment = models.URLField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    client_msg_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pk",)
        indexes = (models.Index(fields=("conversation", "-id"), name="messaging_msg_conv"),)
        constraints = (
            models.UniqueConstraint(
                fields=("sender", "client_msg_id"),
                condition=~models.Q(client_msg_id=""),
                name="messaging_msg_client_id_unique",
            ),
        )

    def __str__(self) -> str:
        return f"{self.conversation_id}#{self.pk}"


class Participant(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="participations"
    )
    last_read_message_id = models.PositiveBigIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=("conversation", "user"), name="messaging_participant_unique"
            ),
        )

    def __str__(self) -> str:
        return f"{self.user_id}@{self.conversation_id}"


class PriceProposal(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="proposals"
    )
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="proposal")
    order_item = models.ForeignKey("orders.OrderItem", on_delete=models.CASCADE, related_name="+")
    previous_price = models.DecimalField(max_digits=10, decimal_places=2)
    proposed_price = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.CharField(max_length=500, blank=True)
    status = models.CharField(
        max_length=12, choices=PROPOSAL_STATUS_CHOICES, default=ProposalStatus.PENDING.value
    )
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self) -> str:
        return f"{self.previous_price} → {self.proposed_price}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=24, choices=NOTIFICATION_KIND_CHOICES)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500)
    link = models.CharField(max_length=255, blank=True)
    conversation = models.ForeignKey(
        Conversation, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = (
            models.Index(
                fields=("recipient", "is_read", "-created_at"), name="messaging_notif_inbox"
            ),
        )

    def __str__(self) -> str:
        return self.title

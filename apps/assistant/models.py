import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField

from apps.assistant.conf import EMBEDDING_DIMENSIONS
from apps.assistant.domain.enums import Role, Sentiment

ROLE_CHOICES = [(role.value, role.value) for role in Role]
SENTIMENT_CHOICES = [(item.value, item.value) for item in Sentiment]


class ProductEmbedding(models.Model):
    product = models.OneToOneField(
        "catalog.Product", on_delete=models.CASCADE, primary_key=True, related_name="+"
    )
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS)
    embedded_text = models.TextField()
    content_hash = models.CharField(max_length=64)
    model_name = models.CharField(max_length=80)
    category_slug = models.CharField(max_length=120, db_index=True)
    current_price = models.DecimalField(max_digits=10, decimal_places=2)
    on_sale = models.BooleanField(default=False)
    in_stock = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "vecteur produit"
        verbose_name_plural = "vecteurs produits"
        indexes = (
            HnswIndex(
                name="assistant_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        )

    def __str__(self) -> str:
        return f"vecteur du produit {self.product_id}"


class AssistantSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assistant_sessions",
    )
    title = models.CharField(max_length=120, blank=True)
    summary = models.TextField(blank=True)
    summarized_count = models.PositiveIntegerField(default=0)
    message_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "conversation assistant"
        verbose_name_plural = "conversations assistant"
        ordering = ("-updated_at",)
        indexes = (models.Index(fields=("user", "-updated_at"), name="assistant_session_user"),)

    def __str__(self) -> str:
        return self.title or str(self.pk)


class AssistantMessage(models.Model):
    session = models.ForeignKey(AssistantSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    product_ids = models.JSONField(default=list, blank=True)
    tool_calls = models.JSONField(default=list, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal(0))
    latency_ms = models.PositiveIntegerField(default=0)
    sentiment = models.CharField(max_length=10, choices=SENTIMENT_CHOICES, blank=True)
    topic = models.CharField(max_length=60, blank=True, db_index=True)
    error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "message assistant"
        verbose_name_plural = "messages assistant"
        ordering = ("created_at", "pk")

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:40]}"

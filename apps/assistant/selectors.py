from collections.abc import Sequence
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.db.models import Avg, Count, Q, QuerySet, Sum
from django.utils import timezone
from pgvector.django import CosineDistance

from apps.assistant.domain.enums import Role, Sentiment
from apps.assistant.domain.queries import LogFilters, ProductQuery
from apps.assistant.domain.read_models import (
    AssistantStats,
    MessageView,
    QuestionLog,
    SessionDetail,
    SessionView,
)
from apps.assistant.models import AssistantMessage, AssistantSession, ProductEmbedding


class VectorSelector:
    def nearest(self, vector: Sequence[float], query: ProductQuery, *, limit: int) -> list[int]:
        candidates = ProductEmbedding.objects.filter(in_stock=True)
        if query.category:
            candidates = candidates.filter(category_slug=query.category)
        if query.on_sale:
            candidates = candidates.filter(on_sale=True)
        if query.max_price is not None:
            candidates = candidates.filter(current_price__lte=query.max_price)
        ranked = candidates.annotate(distance=CosineDistance("embedding", list(vector))).order_by(
            "distance", "product_id"
        )
        return list(ranked.values_list("product_id", flat=True)[:limit])


class SessionSelector:
    def page(self, user_id: int, *, offset: int, limit: int) -> tuple[list[SessionView], int]:
        sessions = AssistantSession.objects.filter(user_id=user_id)
        page = sessions.order_by("-updated_at")[offset : offset + limit]
        return [to_session_view(session) for session in page], sessions.count()

    def detail(self, session: AssistantSession) -> SessionDetail:
        messages = session.messages.exclude(content="").order_by("created_at", "pk")
        return SessionDetail(
            session=to_session_view(session),
            messages=[
                MessageView(
                    id=message.pk,
                    role=Role(message.role),
                    content=message.content,
                    product_ids=tuple(message.product_ids),
                    created_at=message.created_at,
                )
                for message in messages
            ],
        )


class LogSelector:
    def page(
        self, filters: LogFilters, *, offset: int, limit: int
    ) -> tuple[list[QuestionLog], int]:
        questions = _questions(filters)
        page = list(
            questions.select_related("session").order_by("-created_at", "-pk")[
                offset : offset + limit
            ]
        )
        answers = _answers(page)
        return [_log(question, answers.get(question.pk)) for question in page], questions.count()

    def stats(self, filters: LogFilters) -> AssistantStats:
        questions = _questions(filters)
        replies = AssistantMessage.objects.filter(
            role=Role.ASSISTANT.value, session__in=questions.values("session")
        )
        replies = _dated(replies, filters)
        usage = replies.aggregate(
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            cost=Sum("cost"),
            latency=Avg("latency_ms"),
        )
        sentiments = dict(
            questions.exclude(sentiment="").values_list("sentiment").annotate(total=Count("pk"))
        )
        topics = (
            questions.exclude(topic="")
            .values("topic")
            .annotate(total=Count("pk"))
            .order_by("-total", "topic")[:10]
        )
        return AssistantStats(
            questions=questions.count(),
            sessions=questions.values("session").distinct().count(),
            input_tokens=int(usage["input_tokens"] or 0),
            output_tokens=int(usage["output_tokens"] or 0),
            cost=Decimal(usage["cost"] or 0),
            average_latency_ms=int(usage["latency"] or 0),
            sentiments={item.value: int(sentiments.get(item.value, 0)) for item in Sentiment},
            top_topics=[(row["topic"], int(row["total"])) for row in topics],
        )


def to_session_view(session: AssistantSession) -> SessionView:
    return SessionView(
        id=session.pk,
        title=session.title,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _questions(filters: LogFilters) -> QuerySet[AssistantMessage]:
    questions = AssistantMessage.objects.filter(role=Role.USER.value)
    if filters.sentiment is not None:
        questions = questions.filter(sentiment=filters.sentiment.value)
    if filters.topic:
        questions = questions.filter(topic__iexact=filters.topic)
    if filters.search:
        questions = questions.filter(Q(content__icontains=filters.search.strip()))
    return _dated(questions, filters)


def _dated(messages: QuerySet[AssistantMessage], filters: LogFilters) -> QuerySet[AssistantMessage]:
    if filters.date_from is not None:
        messages = messages.filter(created_at__gte=_start(filters.date_from))
    if filters.date_to is not None:
        messages = messages.filter(created_at__lte=_end(filters.date_to))
    return messages


def _answers(questions: list[AssistantMessage]) -> dict[int, AssistantMessage]:
    if not questions:
        return {}
    replies = AssistantMessage.objects.filter(
        role=Role.ASSISTANT.value, session_id__in={question.session_id for question in questions}
    ).order_by("created_at", "pk")
    by_session: dict[UUID, list[AssistantMessage]] = {}
    for reply in replies:
        by_session.setdefault(reply.session_id, []).append(reply)
    answers = {}
    for question in questions:
        later = [
            reply for reply in by_session.get(question.session_id, []) if reply.pk > question.pk
        ]
        if later:
            answers[question.pk] = later[0]
    return answers


def _log(question: AssistantMessage, answer: AssistantMessage | None) -> QuestionLog:
    return QuestionLog(
        id=question.pk,
        session_id=question.session_id,
        user_id=question.session.user_id,
        question=question.content,
        answer=answer.content if answer else "",
        sentiment=Sentiment(question.sentiment) if question.sentiment else None,
        topic=question.topic,
        products_count=len(answer.product_ids) if answer else 0,
        input_tokens=answer.input_tokens if answer else 0,
        output_tokens=answer.output_tokens if answer else 0,
        cost=answer.cost if answer else Decimal(0),
        latency_ms=answer.latency_ms if answer else 0,
        error_code=answer.error_code if answer else "",
        created_at=question.created_at,
    )


def _start(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _end(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.max))

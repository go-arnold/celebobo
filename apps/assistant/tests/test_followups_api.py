import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import ResellerFactory
from apps.assistant.models import AssistantMessage, AssistantSession
from apps.assistant.services.followups import parse_insight

pytestmark = pytest.mark.django_db

SESSIONS = "/api/v1/assistant/sessions/"
LOGS = "/api/v1/bo/assistant/logs/"


def converse(api, questions, capture):
    session_id = api.post(SESSIONS).json()["id"]
    for question in questions:
        with capture(execute=True):
            api.post(
                f"{SESSIONS}{session_id}/messages/?stream=false",
                {"content": question},
                format="json",
            )
    return session_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"sentiment": "positive", "topic": "Prix"}', ("positive", "prix")),
        ('Réponse : {"sentiment": "furieux"}', ("neutral", "")),
        ("pas de json", ("neutral", "")),
    ],
)
def test_parse_insight(raw, expected):
    sentiment, topic = parse_insight(raw)

    assert (sentiment.value, topic) == expected


def test_questions_are_tagged_with_sentiment_and_topic(
    api, catalogue, scripted, django_capture_on_commit_callbacks
):
    converse(api, ["Ma livraison est en retard !"], django_capture_on_commit_callbacks)

    question = AssistantMessage.objects.get(role="user")
    assert (question.sentiment, question.topic) == ("negative", "livraison")


def test_long_conversations_are_summarised(
    api, catalogue, scripted, settings, django_capture_on_commit_callbacks
):
    settings.ASSISTANT = {"PROVIDER": "offline", "MEMORY_MESSAGES": 2, "SUMMARY_EVERY": 2}
    session_id = converse(
        api, ["Bonjour", "Un smartphone ?", "Moins de 300 $"], django_capture_on_commit_callbacks
    )

    session = AssistantSession.objects.get(pk=session_id)
    assert session.summary == "Le client cherche un smartphone à moins de 300 $."
    assert session.summarized_count == 4
    first_system, _ = scripted.seen[0]
    last_system, last_messages = scripted.seen[-1]
    assert "Résumé" not in first_system
    assert "Le client cherche un smartphone" in last_system
    assert len(last_messages) == 2


def test_backoffice_logs_with_cost_and_sentiment(
    as_user, manager, catalogue, scripted, django_capture_on_commit_callbacks
):
    converse(
        APIClient(),
        ["Ma livraison est en retard !", "Et le prix ?"],
        django_capture_on_commit_callbacks,
    )

    body = as_user(manager).get(LOGS).json()

    assert body["meta"]["count"] == 2
    latest = body["results"][0]
    assert latest["question"] == "Et le prix ?"
    assert latest["answer"].startswith("Bonjour !")
    assert latest["products_count"] == 3
    assert latest["output_tokens"] == 300
    stats = body["meta"]["stats"]
    assert stats["questions"] == 2
    assert stats["sessions"] == 1
    assert stats["sentiments"]["negative"] == 2
    assert stats["top_topics"] == [["livraison", 2]]
    assert stats["cost"] == "0.002220"
    assert as_user(manager).get(LOGS, {"sentiment": "positive"}).json()["meta"]["count"] == 0
    assert as_user(manager).get(LOGS, {"search": "prix"}).json()["meta"]["count"] == 1


def test_only_managers_read_the_logs(as_user):
    assert as_user(ResellerFactory.create()).get(LOGS).status_code == 403

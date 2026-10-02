import pytest

from config.celery_routes import route_task


@pytest.mark.parametrize(
    ("name", "args", "queue"),
    [
        ("core.events.dispatch", ("apps.assistant.handlers.follow_up_reply", "e", {}), "ai"),
        ("core.events.dispatch", ("apps.documents.handlers.run_requested_job", "e", {}), "exports"),
        ("documents.purge_jobs", (), "exports"),
        ("core.events.dispatch", ("apps.messaging.handlers.notify", "e", {}), None),
        ("analytics.refresh_sales_facts", (), None),
    ],
)
def test_tasks_are_routed_to_their_queue(name, args, queue):
    route = route_task(name, args, {}, {})

    assert (route or {}).get("queue") == queue

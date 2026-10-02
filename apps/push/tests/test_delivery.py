from types import SimpleNamespace

import pytest
from pywebpush import WebPushException

from apps.accounts.tests.factories import ResellerFactory, UserFactory
from apps.push.adapters import webpush as adapter
from apps.push.adapters.webpush import WebPushSender
from apps.push.conf import PushSettings
from apps.push.domain.messages import DeliveryOutcome, Endpoint, PushMessage
from apps.push.facades import PushFacade
from apps.push.models import PushSubscription
from core.container import container

pytestmark = pytest.mark.django_db

MESSAGE = PushMessage(title="Commande", body="Nouvelle commande", url="https://app.test/o/1")
ENDPOINT = Endpoint(url="https://push.example.com/a", p256dh="key", auth="auth")


def subscribe(user, name):
    return PushSubscription.objects.create(
        user=user, endpoint=f"https://push.example.com/{name}", p256dh="k", auth="a"
    )


def test_dispatch_cleans_up_dead_and_failing_devices(sender, settings):
    settings.PUSH = {**settings.PUSH, "MAX_FAILURES": 2}
    user = UserFactory.create()
    alive, gone, flaky = subscribe(user, "alive"), subscribe(user, "gone"), subscribe(user, "flaky")
    sender.outcomes = {gone.endpoint: DeliveryOutcome.GONE, flaky.endpoint: DeliveryOutcome.FAILED}
    push = container.resolve(PushFacade)

    first = push.send([user.pk], MESSAGE)
    second = push.send([user.pk], MESSAGE)

    assert (first.delivered, first.removed, first.failed) == (1, 1, 1)
    assert (second.delivered, second.removed, second.failed) == (1, 1, 1)
    assert list(PushSubscription.objects.values_list("pk", flat=True)) == [alive.pk]
    assert PushSubscription.objects.get().last_used_at is not None


def test_nothing_is_sent_while_push_is_disabled():
    user = UserFactory.create()
    subscribe(user, "a")

    assert container.resolve(PushFacade).send([user.pk], MESSAGE).delivered == 0


@pytest.mark.parametrize(
    ("status", "outcome"),
    [(None, DeliveryOutcome.DELIVERED), (410, DeliveryOutcome.GONE), (500, DeliveryOutcome.FAILED)],
)
def test_webpush_adapter(monkeypatch, status, outcome):
    calls = []

    def fake_webpush(**request):
        calls.append(request)
        if status is not None:
            raise WebPushException("refused", response=SimpleNamespace(status_code=status))
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(adapter, "webpush", fake_webpush)
    settings = PushSettings(vapid_public_key="pub", vapid_private_key="priv")

    assert WebPushSender(settings).send(ENDPOINT, MESSAGE) is outcome
    assert calls[0]["subscription_info"]["keys"] == {"p256dh": "key", "auth": "auth"}
    assert '"title": "Commande"' in calls[0]["data"]
    assert calls[0]["vapid_claims"] == {"sub": "mailto:contact@celebobo.cd"}


def test_order_notifications_reach_reseller_devices(
    as_user, sender, django_capture_on_commit_callbacks
):
    from apps.accounts.tests.factories import ManagerFactory
    from apps.catalog.tests.factories import ProductFactory
    from apps.orders.tests.conftest import ADDRESS

    reseller = ResellerFactory.create()
    subscribe(reseller, "reseller-phone")
    client = UserFactory.create()
    product = ProductFactory.create(stock=5)
    order = (
        as_user(client)
        .post(
            "/api/v1/orders/",
            {
                "lines": [{"product_id": product.pk, "quantity": 1}],
                "payment_method": "cash",
                "address": ADDRESS,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="push-order-0001",
        )
        .json()
    )

    with django_capture_on_commit_callbacks(execute=True):
        as_user(ManagerFactory.create()).post(
            f"/api/v1/bo/orders/{order['id']}/assign/", {"reseller_id": reseller.pk}, format="json"
        )

    urls = [url for url, _ in sender.sent]
    assert "https://push.example.com/reseller-phone" in urls
    message = next(message for url, message in sender.sent if url.endswith("reseller-phone"))
    assert order["number"] in message.body or order["number"] in message.title
    assert message.url.startswith("http")

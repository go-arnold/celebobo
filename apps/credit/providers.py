from django.utils import timezone

from apps.credit.adapters.gateways import StoreCreditWallet
from apps.credit.facades import StoreCreditFacade
from apps.credit.selectors import CreditSelector
from apps.credit.services.credit import StoreCreditService
from apps.orders.services.contracts import CreditWallet
from core.container import Container, Lifetime


def register(container: Container) -> None:
    container.register(
        CreditWallet,
        lambda _: StoreCreditWallet(StoreCreditService(clock=timezone.now)),
        replace=True,
    )
    container.register(
        StoreCreditFacade,
        lambda _: StoreCreditFacade(
            credit=StoreCreditService(clock=timezone.now),
            selector=CreditSelector(clock=timezone.now),
        ),
        lifetime=Lifetime.TRANSIENT,
    )

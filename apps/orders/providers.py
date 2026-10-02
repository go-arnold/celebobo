from apps.catalog.services.contracts import PurchaseVerifier
from apps.orders.adapters.gateways import (
    AccountsAddressBook,
    AccountsResellerDirectory,
    CatalogInventory,
    DeliveredOrderPurchases,
    NoOrderThreads,
)
from apps.orders.conf import order_settings
from apps.orders.domain.state_machine import OrderStateMachine, TransitionPolicyFactory
from apps.orders.facades import (
    CartFacade,
    CheckoutFacade,
    ClientOrderFacade,
    DispatchFacade,
    OrderAdjustmentFacade,
)
from apps.orders.repositories import CartRepository, OrderRepository
from apps.orders.selectors import OrderSelector
from apps.orders.services.adjustments import AdjustmentService
from apps.orders.services.cart import CartService
from apps.orders.services.checkout import CheckoutService
from apps.orders.services.contracts import AddressBook, Inventory, OrderThreads, ResellerDirectory
from apps.orders.services.lifecycle import OrderLifecycleService
from apps.orders.services.pricing import PricingService
from core.container import Container, Lifetime
from core.events.contracts import EventPublisher


def register(container: Container) -> None:
    container.register(Inventory, lambda _: CatalogInventory())
    container.register(AddressBook, lambda _: AccountsAddressBook())
    container.register(ResellerDirectory, lambda _: AccountsResellerDirectory())
    container.register(OrderThreads, lambda _: NoOrderThreads())
    container.register(OrderStateMachine, lambda _: OrderStateMachine(TransitionPolicyFactory()))
    container.register(PurchaseVerifier, lambda _: DeliveredOrderPurchases(), replace=True)

    container.register(CartFacade, _cart_facade, lifetime=Lifetime.TRANSIENT)
    container.register(CheckoutFacade, _checkout_facade, lifetime=Lifetime.TRANSIENT)
    container.register(ClientOrderFacade, _client_facade, lifetime=Lifetime.TRANSIENT)
    container.register(DispatchFacade, _dispatch_facade, lifetime=Lifetime.TRANSIENT)
    container.register(OrderAdjustmentFacade, _adjustment_facade, lifetime=Lifetime.TRANSIENT)


def _pricing(container: Container) -> PricingService:
    settings = order_settings()
    return PricingService(
        container.resolve(Inventory), settings.shipping_rules, max_lines=settings.max_lines
    )


def _lifecycle(container: Container) -> OrderLifecycleService:
    return OrderLifecycleService(
        OrderRepository(),
        container.resolve(OrderStateMachine),
        container.resolve(Inventory),
        container.resolve(ResellerDirectory),
    )


def _cart_facade(container: Container) -> CartFacade:
    return CartFacade(
        carts=CartService(
            CartRepository(),
            container.resolve(Inventory),
            _pricing(container),
            max_quantity=order_settings().max_quantity,
        )
    )


def _checkout_facade(container: Container) -> CheckoutFacade:
    pricing = _pricing(container)
    return CheckoutFacade(
        checkout=CheckoutService(
            OrderRepository(), pricing, container.resolve(Inventory), container.resolve(AddressBook)
        ),
        pricing=pricing,
        carts=CartRepository(),
        selector=OrderSelector(),
        threads=container.resolve(OrderThreads),
        publisher=container.resolve(EventPublisher),
    )


def _client_facade(container: Container) -> ClientOrderFacade:
    return ClientOrderFacade(
        orders=OrderRepository(),
        lifecycle=_lifecycle(container),
        selector=OrderSelector(),
        threads=container.resolve(OrderThreads),
        publisher=container.resolve(EventPublisher),
    )


def _dispatch_facade(container: Container) -> DispatchFacade:
    return DispatchFacade(
        orders=OrderRepository(),
        lifecycle=_lifecycle(container),
        selector=OrderSelector(),
        resellers=container.resolve(ResellerDirectory),
        threads=container.resolve(OrderThreads),
        publisher=container.resolve(EventPublisher),
    )


def _adjustment_facade(container: Container) -> OrderAdjustmentFacade:
    return OrderAdjustmentFacade(
        adjustments=AdjustmentService(OrderRepository()),
        publisher=container.resolve(EventPublisher),
    )

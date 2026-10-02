from dataclasses import dataclass
from uuid import UUID

from apps.catalog.domain.queries import StockLine
from apps.catalog.domain.read_models import PricedLine
from apps.orders.domain.commands import OrderLineInput
from apps.orders.domain.errors import CartLineNotFound
from apps.orders.domain.read_models import CartLineView, CartView
from apps.orders.models import Cart, CartItem
from apps.orders.repositories import CartRepository
from apps.orders.services.contracts import Inventory
from apps.orders.services.pricing import PricingService, stock_line
from core.domain.errors import DomainError


@dataclass(frozen=True, slots=True)
class CartOwner:
    user_id: int | None = None
    token: UUID | None = None


class CartService:
    def __init__(
        self,
        carts: CartRepository,
        inventory: Inventory,
        pricing: PricingService,
        *,
        max_quantity: int,
    ) -> None:
        self._carts = carts
        self._inventory = inventory
        self._pricing = pricing
        self._max_quantity = max_quantity

    def view(self, owner: CartOwner) -> CartView:
        return self._view(self._find(owner))

    def add(self, owner: CartOwner, line: OrderLineInput) -> CartView:
        self._inventory.price([stock_line(line)])
        cart = self._find(owner) or self._create(owner)
        item = self._carts.add(
            cart, product_id=line.product_id, variant_id=line.variant_id, quantity=line.quantity
        )
        if item.quantity > self._max_quantity:
            self._carts.set_quantity(item, self._max_quantity)
        return self._view(cart)

    def update(self, owner: CartOwner, item_id: int, quantity: int) -> CartView:
        cart = self._find(owner)
        item = self._carts.item(cart, item_id) if cart else None
        if cart is None or item is None:
            raise CartLineNotFound
        self._carts.set_quantity(item, min(quantity, self._max_quantity))
        return self._view(cart)

    def remove(self, owner: CartOwner, item_id: int) -> CartView:
        cart = self._find(owner)
        item = self._carts.item(cart, item_id) if cart else None
        if cart is None or item is None:
            raise CartLineNotFound
        self._carts.remove(item)
        return self._view(cart)

    def clear(self, owner: CartOwner) -> None:
        if cart := self._find(owner):
            self._carts.clear(cart)

    def merge(self, user_id: int, token: UUID) -> CartView:
        guest = self._carts.for_token(token)
        cart = self._carts.ensure_for_user(user_id)
        if guest is not None:
            for item in self._carts.items(guest):
                merged = self._carts.add(
                    cart,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                )
                if merged.quantity > self._max_quantity:
                    self._carts.set_quantity(merged, self._max_quantity)
            self._carts.delete(guest)
        return self._view(cart)

    def _find(self, owner: CartOwner) -> Cart | None:
        if owner.user_id is not None:
            return self._carts.for_user(owner.user_id)
        if owner.token is not None:
            return self._carts.for_token(owner.token)
        return None

    def _create(self, owner: CartOwner) -> Cart:
        if owner.user_id is not None:
            return self._carts.ensure_for_user(owner.user_id)
        return self._carts.create_guest()

    def _view(self, cart: Cart | None) -> CartView:
        items = self._carts.items(cart) if cart else []
        priced: list[PricedLine] = []
        lines: list[CartLineView] = []
        for item in items:
            line = self._price_item(item)
            if line is not None:
                priced.append(line)
            lines.append(
                CartLineView(
                    id=item.pk,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    quantity=item.quantity,
                    available=line is not None,
                )
            )
        return CartView(
            token=str(cart.token) if cart and cart.user_id is None else None,
            lines=tuple(lines),
            quote=self._pricing.view(priced),
        )

    def _price_item(self, item: CartItem) -> PricedLine | None:
        try:
            (line,) = self._inventory.price(
                [
                    StockLine(
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        quantity=item.quantity,
                    )
                ]
            )
        except DomainError:
            return None
        return line

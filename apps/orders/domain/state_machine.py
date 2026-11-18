from dataclasses import dataclass
from typing import Protocol

from apps.orders.domain.enums import FULFILMENT_FLOW, OrderStatus
from core.domain.actor import Actor, Role
from core.domain.errors import InvalidTransition

_STEP = {status: index for index, status in enumerate(FULFILMENT_FLOW)}


@dataclass(frozen=True, slots=True, kw_only=True)
class OrderState:
    status: OrderStatus
    client_id: int
    reseller_id: int | None
    # a quoted zone whose fee the client has not accepted yet: nothing is fixed, so the order
    # cannot be confirmed and the client may still walk away
    awaiting_shipping_quote: bool = False


# the client may cancel free of charge until the shipping quote is accepted
_CLIENT_CANCELLABLE_WHILE_QUOTING = frozenset({OrderStatus.PENDING, OrderStatus.ASSIGNED})


class TransitionPolicy(Protocol):
    def targets(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]: ...


class ClientPolicy:
    def targets(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]:
        if not actor.owns(state.client_id):
            return frozenset()
        cancellable = (
            _CLIENT_CANCELLABLE_WHILE_QUOTING
            if state.awaiting_shipping_quote
            else frozenset({OrderStatus.PENDING})
        )
        return frozenset({OrderStatus.CANCELLED}) if state.status in cancellable else frozenset()


class ResellerPolicy:
    def targets(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]:
        if not actor.owns(state.reseller_id) or state.awaiting_shipping_quote:
            return frozenset()
        return _next_step(state.status)


class StaffPolicy:
    def targets(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]:
        if state.status is OrderStatus.DELIVERED:
            return frozenset({OrderStatus.RETURNED})
        if state.status.is_final:
            return frozenset()
        if state.awaiting_shipping_quote:
            return frozenset({OrderStatus.CANCELLED})
        forward = {
            status
            for status in FULFILMENT_FLOW
            if _STEP[status] > _STEP[state.status] and status is not OrderStatus.ASSIGNED
        }
        return frozenset({*forward, OrderStatus.CANCELLED})


class TransitionPolicyFactory:
    _policies: dict[Role, TransitionPolicy]

    def __init__(self) -> None:
        staff = StaffPolicy()
        self._policies = {
            Role.CLIENT: ClientPolicy(),
            Role.RESELLER: ResellerPolicy(),
            Role.MANAGER: staff,
            Role.ADMIN: staff,
            Role.SYSTEM: staff,
        }

    def for_actor(self, actor: Actor) -> TransitionPolicy:
        return self._policies.get(actor.role, _NoTransitions())


class OrderStateMachine:
    def __init__(self, policies: TransitionPolicyFactory) -> None:
        self._policies = policies

    def allowed(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]:
        return self._policies.for_actor(actor).targets(state, actor)

    def ensure(self, state: OrderState, target: OrderStatus, actor: Actor) -> None:
        if target not in self.allowed(state, actor):
            raise InvalidTransition(
                meta={"from": state.status.value, "to": target.value},
            )


class _NoTransitions:
    def targets(self, state: OrderState, actor: Actor) -> frozenset[OrderStatus]:
        return frozenset()


def _next_step(status: OrderStatus) -> frozenset[OrderStatus]:
    if status not in _STEP or status in (OrderStatus.PENDING, OrderStatus.DELIVERED):
        return frozenset()
    return frozenset({FULFILMENT_FLOW[_STEP[status] + 1]})

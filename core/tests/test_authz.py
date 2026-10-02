from dataclasses import dataclass

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIRequestFactory
from rules.predicates import predicate

from core.api.permissions import requires
from core.authz.catalog import PermissionCatalog
from core.domain.actor import Actor, Role


@dataclass
class Order:
    client_id: int
    reseller_id: int | None


@predicate
def is_order_client(actor: Actor, order: Order) -> bool:
    return actor.owns(order.client_id)


@predicate
def is_assigned_reseller(actor: Actor, order: Order) -> bool:
    return actor.owns(order.reseller_id)


@predicate
def is_staff(actor: Actor, order: Order) -> bool:
    return actor.is_staff


@pytest.fixture
def catalog() -> PermissionCatalog:
    catalog = PermissionCatalog()
    catalog.grant(Role.CLIENT, "orders.view")
    catalog.grant(Role.RESELLER, "orders.status.advance")
    catalog.grant(Role.MANAGER, "orders.assign")
    catalog.grant(Role.ADMIN, "users.manage")
    catalog.restrict("orders.view", is_order_client | is_assigned_reseller | is_staff)
    return catalog


class TestPermissionCatalog:
    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            (Role.ANONYMOUS, set()),
            (Role.CLIENT, {"orders.view"}),
            (Role.RESELLER, {"orders.view", "orders.status.advance"}),
            (Role.MANAGER, {"orders.view", "orders.status.advance", "orders.assign"}),
            (Role.ADMIN, {"orders.view", "orders.status.advance", "orders.assign", "users.manage"}),
        ],
    )
    def test_roles_inherit_lower_grants(self, catalog, role, expected):
        assert catalog.permissions_for(role) == expected

    def test_object_rules_apply_to_objects_only(self, catalog):
        order = Order(client_id=1, reseller_id=2)

        assert catalog.allows(Actor(Role.CLIENT, 9), "orders.view")
        assert catalog.allows(Actor(Role.CLIENT, 1), "orders.view", order)
        assert not catalog.allows(Actor(Role.CLIENT, 9), "orders.view", order)
        assert catalog.allows(Actor(Role.RESELLER, 2), "orders.view", order)
        assert catalog.allows(Actor(Role.MANAGER, 5), "orders.view", order)

    def test_role_grant_is_required_before_object_rule(self, catalog):
        assert not catalog.allows(Actor(Role.CLIENT, 1), "orders.assign")

    def test_unknown_permission_is_a_configuration_error(self, catalog):
        with pytest.raises(ImproperlyConfigured, match="Unknown permission"):
            catalog.allows(Actor(Role.ADMIN, 1), "orders.asign")

        with pytest.raises(ImproperlyConfigured):
            catalog.restrict("missing.permission", is_staff)


class TestRequires:
    def check(self, permission_class, actor, obj=None):
        request = APIRequestFactory().get("/")
        view = type("View", (), {"actor": actor})()
        permission = permission_class()
        if obj is None:
            return permission.has_permission(request, view)
        return permission.has_object_permission(request, view, obj)

    def test_all_permissions_required_by_default(self, catalog):
        permission = requires("orders.view", "orders.assign", catalog=catalog)

        assert self.check(permission, Actor(Role.MANAGER, 1))
        assert not self.check(permission, Actor(Role.RESELLER, 1))

    def test_any_of(self, catalog):
        permission = requires("orders.assign", "users.manage", any_of=True, catalog=catalog)

        assert self.check(permission, Actor(Role.MANAGER, 1))
        assert not self.check(permission, Actor(Role.RESELLER, 1))

    def test_object_level(self, catalog):
        permission = requires("orders.view", catalog=catalog)
        order = Order(client_id=1, reseller_id=None)

        assert self.check(permission, Actor(Role.CLIENT, 1), order)
        assert not self.check(permission, Actor(Role.CLIENT, 2), order)

    def test_readable_name(self, catalog):
        assert requires("orders.view", "orders.assign", catalog=catalog).__name__ == (
            "Requires(orders.view & orders.assign)"
        )

    def test_needs_a_permission(self):
        with pytest.raises(ValueError, match="at least one"):
            requires()

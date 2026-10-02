from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser

from core.api.actor import actor_from_user
from core.domain.actor import Actor, Role


def user(**attributes):
    return SimpleNamespace(
        **{"pk": 5, "is_authenticated": True, "is_superuser": False, **attributes}
    )


@pytest.mark.parametrize("anonymous", [None, AnonymousUser()])
def test_anonymous_users(anonymous):
    assert actor_from_user(anonymous) == Actor.anonymous()


def test_superusers_are_admins():
    assert actor_from_user(user(is_superuser=True)) == Actor(Role.ADMIN, 5)


@pytest.mark.parametrize("role", [Role.CLIENT, Role.RESELLER, Role.MANAGER])
def test_role_attribute_is_used(role):
    assert actor_from_user(user(role=role.value)) == Actor(role, 5)


def test_missing_role_defaults_to_client():
    assert actor_from_user(user()) == Actor(Role.CLIENT, 5)


def test_unknown_role_falls_back_to_client():
    assert actor_from_user(user(role="mukubwa")) == Actor(Role.CLIENT, 5)

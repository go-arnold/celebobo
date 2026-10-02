from typing import Protocol

import pytest
from django.core.exceptions import ImproperlyConfigured

from core.container import Container, Inject, Lifetime
from core.registry import Registry


class Greeter(Protocol):
    def greet(self) -> str: ...


class English:
    def greet(self) -> str:
        return "hello"


class French:
    def greet(self) -> str:
        return "bonjour"


class TestRegistry:
    def test_creates_registered_provider(self):
        registry: Registry[Greeter] = Registry("greeter")
        registry.register("en")(English)

        assert registry.create("en").greet() == "hello"

    def test_rejects_duplicate_keys_unless_replacing(self):
        registry: Registry[Greeter] = Registry("greeter")
        registry.add("en", English)

        with pytest.raises(ImproperlyConfigured, match="already registered"):
            registry.add("en", French)

        registry.add("en", French, replace=True)
        assert registry.create("en").greet() == "bonjour"

    def test_unknown_key_lists_available_providers(self):
        registry: Registry[Greeter] = Registry("greeter")
        registry.add("fr", French)
        registry.add("en", English)

        with pytest.raises(ImproperlyConfigured, match=r"available: en, fr"):
            registry.create("sw")

    def test_membership_and_iteration(self):
        registry: Registry[Greeter] = Registry("greeter")
        registry.add("fr", French)

        assert "fr" in registry
        assert list(registry) == ["fr"]


class TestContainer:
    def test_singleton_is_built_once(self):
        target = Container()
        target.register(Greeter, lambda _: English())

        assert target.resolve(Greeter) is target.resolve(Greeter)

    def test_transient_is_built_each_time(self):
        target = Container()
        target.register(Greeter, lambda _: English(), lifetime=Lifetime.TRANSIENT)

        assert target.resolve(Greeter) is not target.resolve(Greeter)

    def test_factories_can_resolve_dependencies(self):
        target = Container()
        target.register(English, lambda _: English())
        target.register(Greeter, lambda c: c.resolve(English))

        assert target.resolve(Greeter) is target.resolve(English)

    def test_override_is_scoped(self):
        target = Container()
        target.register(Greeter, lambda _: English())

        with target.override(Greeter, French()):
            assert target.resolve(Greeter).greet() == "bonjour"
        assert target.resolve(Greeter).greet() == "hello"

    def test_nested_overrides_restore_previous(self):
        target = Container()
        target.register(Greeter, lambda _: English())
        outer, inner = French(), English()

        with target.override(Greeter, outer):
            with target.override(Greeter, inner):
                assert target.resolve(Greeter) is inner
            assert target.resolve(Greeter) is outer

    def test_unregistered_contract_fails_loudly(self):
        with pytest.raises(ImproperlyConfigured, match="No provider registered for Greeter"):
            Container().resolve(Greeter)

    def test_duplicate_registration_requires_replace(self):
        target = Container()
        target.register(Greeter, lambda _: English())

        with pytest.raises(ImproperlyConfigured):
            target.register(Greeter, lambda _: French())

        target.register(Greeter, lambda _: French(), replace=True)
        assert target.resolve(Greeter).greet() == "bonjour"

    def test_inject_descriptor_resolves_lazily(self):
        target = Container()

        class Service:
            greeter = Inject(Greeter, using=target)

        target.register(Greeter, lambda _: English())
        service = Service()

        assert service.greeter.greet() == "hello"
        with target.override(Greeter, French()):
            assert service.greeter.greet() == "bonjour"
        assert isinstance(Service.greeter, Inject)

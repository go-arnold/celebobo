import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Self, cast, overload

from django.core.exceptions import ImproperlyConfigured


class Lifetime(Enum):
    SINGLETON = auto()
    TRANSIENT = auto()


type Factory[T] = Callable[[Container], T]


@dataclass(frozen=True, slots=True)
class _Provider:
    factory: Callable[["Container"], Any]
    lifetime: Lifetime


_MISSING = object()


class Container:
    def __init__(self) -> None:
        self._providers: dict[type, _Provider] = {}
        self._singletons: dict[type, Any] = {}
        self._overrides: dict[type, Any] = {}
        self._lock = threading.RLock()

    def register[T](
        self,
        contract: type[T],
        factory: Factory[T],
        *,
        lifetime: Lifetime = Lifetime.SINGLETON,
        replace: bool = False,
    ) -> None:
        with self._lock:
            if contract in self._providers and not replace:
                raise ImproperlyConfigured(f"{contract.__qualname__} is already registered")
            self._providers[contract] = _Provider(factory, lifetime)
            self._singletons.pop(contract, None)

    def resolve[T](self, contract: type[T]) -> T:
        if contract in self._overrides:
            return cast(T, self._overrides[contract])
        provider = self._provider_for(contract)
        if provider.lifetime is Lifetime.TRANSIENT:
            return cast(T, provider.factory(self))
        with self._lock:
            if contract not in self._singletons:
                self._singletons[contract] = provider.factory(self)
            return cast(T, self._singletons[contract])

    def is_registered(self, contract: type) -> bool:
        return contract in self._providers or contract in self._overrides

    @contextmanager
    def override[T](self, contract: type[T], instance: T) -> Iterator[T]:
        previous = self._overrides.get(contract, _MISSING)
        self._overrides[contract] = instance
        try:
            yield instance
        finally:
            if previous is _MISSING:
                self._overrides.pop(contract, None)
            else:
                self._overrides[contract] = previous

    def reset_singletons(self) -> None:
        with self._lock:
            self._singletons.clear()

    def _provider_for(self, contract: type) -> _Provider:
        try:
            return self._providers[contract]
        except KeyError:
            raise ImproperlyConfigured(
                f"No provider registered for {contract.__qualname__}"
            ) from None


class Inject[T]:
    def __init__(self, contract: type[T], *, using: Container | None = None) -> None:
        self._contract = contract
        self._container = using

    @overload
    def __get__(self, instance: None, owner: type[Any]) -> Self: ...

    @overload
    def __get__(self, instance: object, owner: type[Any]) -> T: ...

    def __get__(self, instance: object | None, owner: type[Any]) -> T | Self:
        if instance is None:
            return self
        return (self._container or container).resolve(self._contract)


container = Container()

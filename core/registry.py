from collections.abc import Callable, Iterator

from django.core.exceptions import ImproperlyConfigured

type Builder[T] = Callable[[], T]


class Registry[T]:
    def __init__(self, name: str) -> None:
        self._name = name
        self._builders: dict[str, Builder[T]] = {}

    def register(self, key: str, *, replace: bool = False) -> Callable[[Builder[T]], Builder[T]]:
        def decorator(builder: Builder[T]) -> Builder[T]:
            self.add(key, builder, replace=replace)
            return builder

        return decorator

    def add(self, key: str, builder: Builder[T], *, replace: bool = False) -> None:
        if key in self._builders and not replace:
            raise ImproperlyConfigured(f"{self._name}: provider '{key}' is already registered")
        self._builders[key] = builder

    def create(self, key: str) -> T:
        try:
            builder = self._builders[key]
        except KeyError:
            available = ", ".join(self) or "none"
            raise ImproperlyConfigured(
                f"{self._name}: unknown provider '{key}' (available: {available})"
            ) from None
        return builder()

    def __contains__(self, key: object) -> bool:
        return key in self._builders

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._builders))

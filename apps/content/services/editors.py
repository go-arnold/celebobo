from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from django.db.models import Model

from apps.content.repositories import ModelRepository
from core.domain.errors import DomainError
from core.domain.values import provided

type Validator[M] = Callable[[M | None, dict[str, Any]], None]


def accept_all(_instance: Any, _values: dict[str, Any]) -> None:
    return None


class Editor[M: Model]:
    def __init__(
        self,
        repository: ModelRepository[M],
        *,
        not_found: type[DomainError],
        validate: Validator[M] = accept_all,
    ) -> None:
        self._repository = repository
        self._not_found = not_found
        self._validate = validate

    def create(self, fields: Any) -> M:
        values = asdict(fields)
        self._validate(None, values)
        return self._repository.create(**values)

    def update(self, pk: int, changes: Any) -> M:
        instance = self.get(pk, for_update=True)
        values = dict(provided(changes))
        self._validate(instance, values)
        for name, value in values.items():
            setattr(instance, name, value)
        if values:
            self._repository.save(instance, fields=values)
        return instance

    def delete(self, pk: int) -> None:
        self._repository.delete(self.get(pk, for_update=True))

    def get(self, pk: int, *, for_update: bool = False) -> M:
        instance = self._repository.get(pk, for_update=for_update)
        if instance is None:
            raise self._not_found
        return instance

import types
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import UUID

from core.events.base import DomainEvent

type JSONValue = bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None

_MAPPING_ARITY = 2

_SCALAR_DECODERS: Mapping[type, Any] = {
    datetime: datetime.fromisoformat,
    date: date.fromisoformat,
    UUID: UUID,
    Decimal: Decimal,
}


def encode(event: DomainEvent) -> dict[str, JSONValue]:
    return {item.name: _encode(getattr(event, item.name)) for item in fields(event)}


def decode[E: DomainEvent](event_type: type[E], payload: Mapping[str, Any]) -> E:
    hints = get_type_hints(event_type)
    values = {
        item.name: _decode(payload[item.name], hints[item.name])
        for item in fields(event_type)
        if item.name in payload
    }
    return event_type(**values)


def _encode(value: Any) -> JSONValue:
    match value:
        case Enum():
            return _encode(value.value)
        case datetime() | date():
            return value.isoformat()
        case UUID() | Decimal():
            return str(value)
        case Mapping():
            return {str(key): _encode(item) for key, item in value.items()}
        case list() | tuple() | set() | frozenset():
            return [_encode(item) for item in value]
        case None | bool() | int() | float() | str():
            return value
        case _:
            raise TypeError(f"Cannot encode {type(value).__name__} in a domain event")


def _decode(value: Any, hint: Any) -> Any:
    if value is None:
        return None
    origin = get_origin(hint)
    if origin in (Union, types.UnionType):
        candidates = [arg for arg in get_args(hint) if arg is not type(None)]
        return _decode(value, candidates[0]) if len(candidates) == 1 else value
    if origin is not None:
        return _decode_generic(value, origin, get_args(hint))
    if isinstance(hint, type):
        if issubclass(hint, Enum):
            return hint(value)
        if decoder := _SCALAR_DECODERS.get(hint):
            return decoder(value)
    return value


def _decode_generic(value: Any, origin: Any, args: tuple[Any, ...]) -> Any:
    if origin in (dict, Mapping):
        value_hint = args[1] if len(args) == _MAPPING_ARITY else Any
        return {key: _decode(item, value_hint) for key, item in value.items()}
    item_hint = args[0] if args else Any
    items = [_decode(item, item_hint) for item in value]
    if origin is list:
        return items
    if origin in (frozenset, set, AbstractSet):
        return frozenset(items)
    if origin in (tuple, Sequence):
        return tuple(items)
    return value

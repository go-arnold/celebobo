from collections.abc import Mapping
from dataclasses import fields
from enum import Enum
from typing import Any, Final


class Unset(Enum):
    UNSET = "unset"

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = Unset.UNSET

type Maybe[T] = T | Unset


def provided(command: Any) -> Mapping[str, Any]:
    return {
        item.name: getattr(command, item.name)
        for item in fields(command)
        if getattr(command, item.name) is not UNSET
    }

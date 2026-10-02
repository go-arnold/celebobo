from collections.abc import Awaitable, Callable
from typing import cast

from channels.db import database_sync_to_async


def db_call[**P, R](fn: Callable[P, R]) -> Callable[P, Awaitable[R]]:
    return cast(Callable[P, Awaitable[R]], database_sync_to_async(fn))

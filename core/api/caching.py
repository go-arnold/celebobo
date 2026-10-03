from collections.abc import Callable
from functools import wraps
from http import HTTPStatus
from typing import Any

from django.utils.cache import patch_cache_control
from rest_framework.response import Response

type ViewMethod = Callable[..., Response]

PUBLIC_MAX_AGE = 60
PUBLIC_STALE_WHILE_REVALIDATE = 300


def public_cache(method: ViewMethod) -> ViewMethod:
    @wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> Response:
        response = method(*args, **kwargs)
        if response.status_code == HTTPStatus.OK:
            patch_cache_control(
                response,
                public=True,
                max_age=PUBLIC_MAX_AGE,
                s_maxage=PUBLIC_MAX_AGE,
                stale_while_revalidate=PUBLIC_STALE_WHILE_REVALIDATE,
            )
        return response

    return wrapper

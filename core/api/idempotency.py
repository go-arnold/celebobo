import hashlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, Concatenate, cast

from django.core.cache import caches
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.conf import core_settings
from core.container import container
from core.domain.errors import BusinessRuleViolation, Conflict, ValidationFailed

IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
SUCCESS_UPPER_BOUND = 300
_KEY = re.compile(r"^[\x21-\x7e]{8,255}$")

type ViewAction[V: APIView, **P] = Callable[Concatenate[V, Request, P], Response]


class IdempotencyKeyReused(BusinessRuleViolation):
    default_code = "idempotency_key_reused"
    default_detail = "Cette clé d'idempotence a déjà été utilisée pour une autre requête."


class IdempotencyInProgress(Conflict):
    default_code = "idempotency_in_progress"
    default_detail = "Une requête avec cette clé d'idempotence est déjà en cours."


@dataclass(frozen=True, slots=True)
class StoredResponse:
    fingerprint: str
    status: int
    data: Any


class IdempotencyStore:
    def __init__(self, *, cache_alias: str, ttl: int, lock_ttl: int) -> None:
        self._cache_alias = cache_alias
        self._ttl = ttl
        self._lock_ttl = lock_ttl

    @classmethod
    def from_settings(cls) -> "IdempotencyStore":
        settings = core_settings()
        return cls(
            cache_alias=settings.idempotency_cache,
            ttl=settings.idempotency_ttl,
            lock_ttl=settings.idempotency_lock_ttl,
        )

    def get(self, scope: str) -> StoredResponse | None:
        stored = caches[self._cache_alias].get(self._response_key(scope))
        return stored if isinstance(stored, StoredResponse) else None

    def save(self, scope: str, response: StoredResponse) -> None:
        caches[self._cache_alias].set(self._response_key(scope), response, timeout=self._ttl)

    @contextmanager
    def lock(self, scope: str) -> Iterator[None]:
        cache = caches[self._cache_alias]
        key = f"core:idempotency:lock:{scope}"
        if not cache.add(key, 1, timeout=self._lock_ttl):
            raise IdempotencyInProgress
        try:
            yield
        finally:
            cache.delete(key)

    @staticmethod
    def _response_key(scope: str) -> str:
        return f"core:idempotency:response:{scope}"


def idempotent[V: APIView, **P](
    *, required: bool = True
) -> Callable[[ViewAction[V, P]], ViewAction[V, P]]:
    def decorator(action: ViewAction[V, P]) -> ViewAction[V, P]:
        @wraps(action)
        def wrapper(view: V, request: Request, *args: P.args, **kwargs: P.kwargs) -> Response:
            key = request.headers.get(IDEMPOTENCY_HEADER)
            if key is None and not required:
                return action(view, request, *args, **kwargs)
            _validate_key(key)
            store = container.resolve(IdempotencyStore)
            scope = _scope(request, str(key))
            fingerprint = _fingerprint(request)
            if (stored := store.get(scope)) is not None:
                return _replay(stored, fingerprint)
            with store.lock(scope):
                if (stored := store.get(scope)) is not None:
                    return _replay(stored, fingerprint)
                response = action(view, request, *args, **kwargs)
                if response.status_code < SUCCESS_UPPER_BOUND:
                    store.save(
                        scope,
                        StoredResponse(fingerprint, response.status_code, _plain(response.data)),
                    )
                return response

        return cast(ViewAction[V, P], wrapper)

    return decorator


def _validate_key(key: str | None) -> None:
    if key is None:
        raise ValidationFailed(
            "L'en-tête Idempotency-Key est requis.",
            errors={IDEMPOTENCY_HEADER: ["Ce champ est obligatoire."]},
        )
    if not _KEY.fullmatch(key):
        raise ValidationFailed(
            "L'en-tête Idempotency-Key est invalide.",
            errors={IDEMPOTENCY_HEADER: ["8 à 255 caractères ASCII imprimables."]},
        )


def _scope(request: Request, key: str) -> str:
    principal = request.user.pk if request.user and request.user.is_authenticated else "anonymous"
    raw = f"{principal}|{request.method}|{request.path}|{key}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _fingerprint(request: Request) -> str:
    body = json.dumps(request.data, cls=DjangoJSONEncoder, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def _replay(stored: StoredResponse, fingerprint: str) -> Response:
    if stored.fingerprint != fingerprint:
        raise IdempotencyKeyReused
    return Response(stored.data, status=stored.status, headers={REPLAYED_HEADER: "true"})


def _plain(data: Any) -> Any:
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))

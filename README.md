# Celebobo API

Django REST + Channels backend for Celebobo. The architecture, the data model and the endpoint plan are in [`docs/BACKEND_PLAN.md`](docs/BACKEND_PLAN.md).

## Setup

```bash
uv sync
cp .env.example .env
uv run pytest
uv run pre-commit install
```

## Quality gates

```bash
uv run ruff format --check . && uv run ruff check .
uv run mypy .
uv run lint-imports
uv run bandit -q -c pyproject.toml -r core config
uv run pytest --cov
```

## `core` at a glance

| Module | Responsibility |
|---|---|
| `core.registry.Registry[T]` | Named factories for interchangeable implementations, selected from settings |
| `core.container` | `Container` (singleton/transient providers, `override()` for tests) and the `Inject` descriptor |
| `core.events` | `DomainEvent`, `@domain_event`, `EventBus` (observer, published after commit, inline or Celery handlers, deduplicated) |
| `core.observability` | `@use_case` / `@logged_facade`, the structlog setup, request-id middleware, `Metrics` backends, Celery context propagation |
| `core.authz` | `PermissionCatalog`: role grants inherited by higher roles, plus object rules (django-rules predicates) |
| `core.api` | `UseCaseViewSet`, `SelectorViewSet`, `requires()`, `paginated()`, `@idempotent()`, problem+json errors, versioned routing |
| `core.health` | `/health/live/`, `/health/ready/` with registered checks |
| `core.domain` | Framework-free primitives: `Actor`, `Role`, `Money`, `DomainError` hierarchy |
| `core.testing` | Fakes and pytest fixtures (`published_events`, `recorded_metrics`, `make_actor`) |

Every app follows the same conventions:
- An app exposes its endpoints in `api/v1/urls.py`; they are mounted automatically under `/api/v1/`.
- An app grants permissions in `permissions.py` and subscribes to events in `handlers.py`; both modules are discovered automatically.

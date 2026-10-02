# Celebobo API

Django REST + Channels backend for Celebobo. The architecture, the data model and the endpoint plan are in [`docs/BACKEND_PLAN.md`](docs/BACKEND_PLAN.md).

## Setup

```bash
uv sync
cp .env.example .env
docker run -d --name celebobo-pg -e POSTGRES_USER=celebobo -e POSTGRES_PASSWORD=celebobo -e POSTGRES_DB=celebobo -p 5432:5432 postgres:16-alpine
uv run pytest            # the test suite needs PostgreSQL (TEST_DATABASE_URL overrides the default)
uv run pre-commit install
```

## Running

```bash
uv run python manage.py migrate
uv run uvicorn config.asgi:application --reload          # HTTP and WebSocket
uv run celery -A config worker -l info                   # background handlers and email
```

## Quality gates

```bash
uv run ruff format --check . && uv run ruff check .
uv run mypy .
uv run lint-imports
uv run bandit -q -c pyproject.toml -r core config apps
DJANGO_SETTINGS_MODULE=config.settings.test uv run python manage.py spectacular --validate --fail-on-warn --file openapi.yml
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

## Apps

### `apps.accounts`

Custom `User` (email login, role, reseller referral code, availability, commission rate), the address book and notification preferences.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/register/` | Registration through `AccountFacade`; the verification email goes out in the background |
| `POST /api/v1/auth/login/` · `logout/` · `token/refresh/` | dj-rest-auth with JWTs in httpOnly cookies (`cb_access`, `cb_refresh`) and CSRF enforced |
| `GET /api/v1/auth/csrf/` | Sets the `csrftoken` cookie |
| `POST /api/v1/auth/email/verify/` · `email/resend/` | Email verification; the link points to `FRONTEND_URL/verifier-email/<key>` |
| `POST /api/v1/auth/password/reset/` · `reset/confirm/` · `change/` | Password flows; the reset link points to `FRONTEND_URL/reinitialiser-mot-de-passe?uid=…&token=…` |
| `POST /api/v1/auth/social/google/` | Google sign-in (`access_token`, `code` or `id_token`) |
| `GET /api/v1/auth/referral-codes/<code>/validate/` | Live check of a reseller code |
| `POST /api/v1/auth/ws-ticket/` | Single-use WebSocket ticket (30 s) |
| `GET · PATCH · DELETE /api/v1/me/` | Profile; deleting anonymizes the account and revokes its tokens |
| `/api/v1/me/addresses/` (+ `<id>/`, `<id>/set-default/`) | Address book with exactly one default address |
| `GET · PATCH /api/v1/me/notification-preferences/` | Per-topic email and push toggles |
| `POST /api/v1/bo/users/<id>/role/` | Admin only: change a role (promoting to reseller issues a code) |
| `PATCH /api/v1/bo/me/availability/` | Reseller only: online, away or offline |

### `apps.catalog`

Categories, products (variants, options, images, features), the stock movement log, reviews and favourites. Products and categories use soft deletes. Search uses PostgreSQL full-text search, read through the `SearchEngine` and `SearchIndex` contracts (`postgres` adapters):
- `Product.search_vector` is a pre-computed `SearchVectorField` with a GIN index. Weights: name A, category B, features C, description D.
- It uses the `french_unaccent` text configuration (the `unaccent` extension plus French stemming), so "ecouteur" finds "Écouteurs".
- Listing uses `websearch_to_tsquery` (quotes and `-word` work) ranked with `ts_rank`; autocomplete uses prefix tsqueries (`ipho:*`).
- `ProductChanged` updates the vector inline, and `manage.py catalog_reindex` rebuilds every vector.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/categories/` · `<slug>/` | Active categories with visible product counts |
| `GET /api/v1/products/` | `search`, `category`, `ids`, `on_sale`, `in_stock`, `badge`, `min_price`, `max_price`, `ordering`, `page`, `page_size` |
| `GET /api/v1/products/facets/` | Category counts, price range, stock and sale counts for the same filters |
| `GET /api/v1/products/<slug>/` · `related/` | Product detail (variants, options, care instructions) and related products |
| `GET /api/v1/search/suggest/?q=` | Autocomplete |
| `GET · POST /api/v1/products/<slug>/reviews/` · `eligibility/` | Reviews with a rating summary; only verified buyers can post |
| `GET · POST /api/v1/me/favorites/` · `DELETE <product_id>/` | Favourites |

Reads are cached in `CatalogCache`, which is invalidated by `ProductChanged`, `ProductRemoved`, `CategoryChanged` and `ReviewPosted`. Edits made in Django admin publish the same events.

### `apps.orders`

Cart, pricing, idempotent checkout, the order state machine, reseller dispatch and public tracking. Orders reaches other apps only through ports:

| Port | Default adapter |
|---|---|
| `Inventory` | the catalogue's `InventoryFacade` (prices lines, reserves and releases stock with row locks) |
| `AddressBook`, `ResellerDirectory` | public accounts selectors |
| `OrderThreads` | `NoOrderThreads` until the messaging app provides conversations |

Orders also replaces the catalogue's `PurchaseVerifier`, so delivered orders unlock verified reviews.

Status flow: `pending → assigned → confirmed → paid → shipping → delivered`, plus `cancelled` and `returned`. `TransitionPolicyFactory` picks the policy for each role:
- the client can cancel only while the order is pending;
- the assigned reseller moves one step forward at a time;
- managers can make any forward move, cancel, or return a delivered order.

Cancellations and returns put the stock back.

| Endpoint | Purpose |
|---|---|
| `GET · DELETE /api/v1/cart/` · `POST cart/items/` · `PATCH · DELETE cart/items/<id>/` | Server cart; guests use the `X-Cart-Token` header |
| `POST /api/v1/cart/merge/` | Merge a guest cart into the user's cart at login |
| `POST /api/v1/checkout/quote/` | Price lines, shipping fee and the amount left before free shipping |
| `POST /api/v1/orders/` | Place an order (`Idempotency-Key` required) |
| `GET /api/v1/me/orders/` · `<number>/` · `POST <number>/cancel/` | The client's orders |
| `POST /api/v1/orders/track/` | Public tracking with the order number plus email or phone |
| `GET /api/v1/bo/orders/` · `<id>/` | Back-office list (counts per status; resellers see only their assignments) and detail with allowed transitions |
| `POST /api/v1/bo/orders/<id>/assign/` · `decline/` · `transition/` | Dispatch and status changes |
| `GET /api/v1/bo/resellers/assignable/` | Resellers with availability and current workload |

### `apps.messaging`

Order and support conversations, messages with read tracking, price proposals, and notifications (in-app and email).

**Order threads**
- Messaging implements the orders `OrderThreads` port, so every order gets its thread inside the checkout transaction.
- Inline handlers on order events add or remove the assigned reseller and close the thread when the order reaches a final status.

**Price proposals**
- The assigned reseller or a manager proposes a new unit price for an item. The order must be `assigned` or `confirmed`, and the price can't exceed the catalogue price.
- Only the client answers. Accepting reprices the item through `OrderAdjustmentFacade`, which recomputes the totals and publishes `OrderRepriced`.

**Notifications**
- Background handlers turn order and messaging events into notifications through `NotificationRouter`, then `NotificationFanout`.
- The channels come from `notifier_registry` (`MESSAGING.NOTIFICATION_CHANNELS`): `in_app` (stored and announced with `NotificationCreated`) and `email` (sent according to each user's preferences, through `core.mail`).
- "New message" alerts are deduplicated: only one unread alert per conversation.

| Endpoint | Purpose |
|---|---|
| `GET · POST /api/v1/conversations/` | List (`kind`, `status`, `unread`, `search`) or open a support conversation |
| `GET /api/v1/conversations/<id>/` | Header with the last message and the unread count |
| `GET · POST /api/v1/conversations/<id>/messages/` | History (`before` cursor, `limit`) or send a message (`client_msg_id` makes retries safe) |
| `POST /api/v1/conversations/<id>/read/` | Mark as read up to a message |
| `POST /api/v1/conversations/<id>/close/` · `reopen/` · `assign/` | Moderation; `assign` is for managers and support threads only |
| `POST /api/v1/conversations/<id>/price-proposals/` | Propose a price for an order item |
| `POST /api/v1/price-proposals/<id>/respond/` | The client accepts or refuses |
| `GET /api/v1/notifications/` · `unread-counts/` | Inbox and header badges |
| `POST /api/v1/notifications/<id>/read/` · `read-all/` | Mark notifications as read |

### `apps.realtime`

The WebSocket gateway is served by Channels at `wss://<api>/ws/?ticket=<ticket>`. Clients get the ticket from `POST /api/v1/auth/ws-ticket/`; it's single-use and expires after 30 s. The browser's `Origin` must be in `WEBSOCKET_ALLOWED_ORIGINS`. Each connection joins `user.<id>`; staff also join `staff`. Every message uses the envelope `{type, data, ref}`.

The consumer only parses envelopes, checks access, and calls the same facades as the REST API: a message sent over the socket and one posted over REST go through the same code.

**Server pushes:** `RealtimeObserver` (`handlers.py`) maps domain events to groups through `RealtimeRelay`, which uses the `Broadcaster` contract (Channels layer adapter). Nothing else talks to the channel layer, apart from typing indicators sent by the consumer.

| Client → server | Effect |
|---|---|
| `conversation.subscribe` / `unsubscribe` | Join or leave `conversation.<id>` (access checked) |
| `message.send` | Post a message; replies `message.ack` with `client_msg_id` |
| `typing.start` / `typing.stop` | `conversation.typing` to the other subscribers |
| `message.read` | Read receipt, plus `unread.counts` for the reader |
| `presence.ping` | Keeps a reseller's presence alive; replies `presence.pong` |

**Server → client events:**
- messages and conversations: `message.created`, `conversation.updated`, `conversation.read`, `conversation.closed`, `conversation.reopened`, `conversation.assigned`;
- notifications: `notification.created`, `unread.counts`;
- orders: `order.created`, `order.assigned`, `order.status_changed`, `order.updated`;
- presence: `presence.changed`;
- errors: `error`, carrying the same `code` values as the REST API.

**Limits and presence**
- Each connection has a token bucket (`REALTIME.BURST`). Once it's empty, messages are answered with `rate_limited`.
- Reseller presence counts connections per user, so several tabs are fine. Staff get `presence.changed` when a reseller comes online or goes offline.
- `GET /api/v1/bo/presence/?ids=` returns which resellers are online (managers only).

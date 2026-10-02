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

#### Back-office catalogue

Managers (`products.manage`, `stock.adjust`, `categories.manage`, `reviews.moderate`) manage the catalogue. Resellers can read it (`products.view`).

**What's enforced**
- Slugs are generated and kept unique.
- Prices are validated (the sale price must be below the price; the cost price can't be negative).
- Variant attributes must match the product's options. SKUs are generated (`CB-<product>-<n>`) or validated as unique.
- A product's stock is the sum of its active variants' stock.
- Every stock change is an append-only `StockMovement`. Going at or below the threshold publishes `StockLow`, which is pushed to staff as `stock.low`.
- Images are referenced by uploaded media id (see `apps.media`), never by a raw URL.

| Endpoint | Purpose |
|---|---|
| `GET · POST /api/v1/bo/products/` | List (`search` also matches SKU, `category_id`, `status=active\|inactive\|trash\|all`, `on_sale`, `out_of_stock`, `low_stock`, `badge`, price range; `meta.stats`) or create |
| `GET · PATCH · DELETE /api/v1/bo/products/<id>/` · `restore/` · `duplicate/` | Detail with cost and margin, edit, soft delete, restore, copy (created inactive) |
| `POST /api/v1/bo/products/bulk/` | `activate`, `deactivate`, `trash`, `restore`, `set_category`, `set_discount` (1–90 %), `clear_discount` |
| `POST /api/v1/bo/products/<id>/variants/` · `PATCH · DELETE /api/v1/bo/variants/<id>/` | Variants; deleting a variant that has stock history deactivates it instead |
| `POST /api/v1/bo/products/<id>/stock-adjustments/` · `GET stock-movements/` | Adjust stock by `delta` or `set`, with a reason; movement history |
| `GET /api/v1/bo/stock/alerts/` | Products and variants at or below their threshold |
| `GET · POST /api/v1/bo/categories/` · `PATCH · DELETE <id>/?move_to=` · `POST reorder/` | Categories; deleting a non-empty category without `move_to` returns 409 with `products_count` |
| `GET /api/v1/bo/reviews/` · `PATCH <id>/` | Review moderation (`published` or `hidden`); the product's rating is recomputed |

### `apps.media`

Cloudinary signed direct uploads, no SDK. The browser uploads straight to Cloudinary; the API only signs the request and verifies the result.

1. `POST /api/v1/uploads/sign/ {purpose}` returns the upload URL, API key, timestamp, folder, allowed formats, incoming transformation (resizing and `q_auto` compression) and signature. The API secret is never sent.
2. The browser uploads the file directly to Cloudinary with those parameters.
3. `POST /api/v1/uploads/complete/` sends Cloudinary's response (`public_id`, `version`, `signature`, `format`, `bytes`, …). The API checks:
   - the response signature;
   - that the `public_id` is inside the signed folder;
   - the format and size limits.

   It then stores an `UploadedMedia` and rebuilds the delivery URL itself.

| Purpose | Permission | Max size | Transformation |
|---|---|---|---|
| `product_image` | `products.manage` | 8 MB | `c_limit,w_1600,h_1600/q_auto:good` |
| `category_image` | `categories.manage` | 4 MB | `c_limit,w_1200,h_1200/q_auto:good` |
| `avatar` | `media.upload` | 2 MB | `c_fill,g_face,w_400,h_400/q_auto` |
| `message_attachment` | `media.upload` | 5 MB | `c_limit,w_1600,h_1600/q_auto` |

Configure with `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` and `CLOUDINARY_ROOT_FOLDER`. While these are missing, signing returns 503 `storage_not_configured`.

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
- sales (seller and staff): `sale.created`, `sale.updated`, `sale.deleted`;
- commissions (the reseller): `commission.updated`, `payout.created`;
- reseller programme (staff): `reseller_application.created`;
- errors: `error`, carrying the same `code` values as the REST API.

**Limits and presence**
- Each connection has a token bucket (`REALTIME.BURST`). Once it's empty, messages are answered with `rate_limited`.
- Reseller presence counts connections per user, so several tabs are fine. Staff get `presence.changed` when a reseller comes online or goes offline.
- `GET /api/v1/bo/presence/?ids=` returns which resellers are online (managers only).

### `apps.sales`

Back-office sales, order-to-sale conversion, refunds and returns, reseller commissions and payouts. Sales reaches other apps only through ports:

| Port | Default adapter |
|---|---|
| `Inventory` | the catalogue's `InventoryFacade` (prices, cost, stock moves, sales counter) |
| `OrderBook` | public orders selectors, plus `DispatchFacade` to mark converted orders delivered |
| `Sellers` | public accounts `SellerSelector` |

**Recording**
- A reseller always sells for themselves. Managers can attribute a sale to a reseller with `seller_id`; without one, the sale is theirs and earns no commission.
- The product's cost is frozen on the sale, so profit doesn't change when the catalogue cost does. Stock moves with reason `sale`.
- `bulk/` records up to 50 lines in one transaction. When a line fails, nothing is saved and the error carries `meta.line`.

**Conversion**
- Confirmed, paid, shipping and delivered orders can be converted. Each order item becomes one sale, and the stock is left alone because the order already reserved it.
- An order item can only be converted once (one-to-one link), so a repeated conversion returns `409 already_converted`.
- The seller is the assigned reseller, and the order is marked delivered if it isn't yet.

**Refunds and returns**
- `refund` is a partial or full amount and leaves the stock alone. `return` refunds what's left and restocks.
- Sales that came from an order are returned through the order (`returned` status). An inline handler then marks its sales returned, without restocking a second time.

**Commissions**
- A sale by a reseller earns `total × rate` at the reseller's current rate, and the rate is frozen in the ledger entry.
- Refunds reverse the commission proportionally. Returns, deletions and price edits void or rebase it.
- The balance due is the sum of the entries minus the payouts. A payout can't exceed it.

| Endpoint | Purpose |
|---|---|
| `GET · POST /api/v1/bo/sales/` | List with filters (`period`, `date_from`, `date_to`, `payment_method`, `seller_id`, `product_id`, `status`, `search`) and `meta.stats` (revenue, profit, count, units, average); record a sale (`Idempotency-Key`) |
| `POST /api/v1/bo/sales/bulk/` | Record several sales atomically |
| `GET · PATCH · DELETE /api/v1/bo/sales/<id>/` | Detail with refunds, edit (valid sales only), delete (admins) |
| `POST /api/v1/bo/sales/<id>/refund/` | Refund or return (managers) |
| `GET /api/v1/bo/orders/convertible/` | Orders that can be converted, flagged when already converted |
| `POST /api/v1/bo/orders/<id>/convert-to-sales/` | Convert, with optional price overrides per item |
| `GET /api/v1/bo/commissions/` · `summary/` · `series/` | Ledger, balance and 6-month series; staff pass `reseller_id` |
| `GET /api/v1/bo/commissions/overview/` | Balances of every reseller (managers) |
| `GET · POST /api/v1/bo/payouts/` | Payout history; record a payout (admins) |

Permissions:
- resellers: `sales.view.own`, `sales.create`, `sales.convert`, `sales.edit.own`, `commissions.view.own`;
- managers: `sales.view.all`, `sales.edit.all`, `sales.refund`, `commissions.view.all`;
- admins: `sales.delete`, `commissions.pay`.

### `apps.resellers`

The reseller programme: applications from `/devenir-revendeur`, the reseller directory for staff, and each reseller's referral kit. Account changes stay in accounts (`ResellerAccountFacade`), so this app only reaches other apps through ports:

| Port | Default adapter |
|---|---|
| `ResellerAccounts` | accounts `ResellerAccountFacade` (onboard, update, activate, password setup link) |
| `ResellerDirectory` | accounts `ResellerDirectorySelector` |
| `SalesLedger` | sales `seller_performance` and `top_sellers` |
| `InviteeOrders` | orders `client_order_totals` (cancelled and returned orders excluded) |
| `QrRenderer` | `segno`, as an SVG data URI |

**Applications**
- Anyone can apply (throttled to `reseller_applications`); a signed-in applicant is linked to the application. There is one pending application per email, and active resellers can't apply.
- Approving onboards the account. A new email gets a reseller account without a password and a verified address; an existing client is promoted and keeps their account. Staff accounts can't become resellers.
- Onboarding issues a referral code and sets the commission rate (default 7 %) and the optional manager.
- Emails go out in background handlers: an acknowledgement, a welcome email (with a password setup link for new accounts), or the rejection with its reason.

**Directory**
- Each reseller row carries `performance`: sales count, net revenue, commission earned and commission due.
- Deactivating a reseller sets them offline and revokes their refresh tokens.
- A reseller's sales and commissions come from `bo/sales/?seller_id=` and `bo/commissions/?reseller_id=`.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/reseller-applications/` | Public application form |
| `GET /api/v1/bo/reseller-applications/` · `<id>/` | Review queue (`status`, `search`, `meta.counts` per status) |
| `POST /api/v1/bo/reseller-applications/<id>/approve/` · `reject/` | Approve (`commission_rate`, `manager_id`) or reject (`reason`) |
| `GET /api/v1/bo/resellers/` | Directory (`search`, `active`, `manager_id`, `ordering`: `name`, `-joined`, `joined`, `-invited`, `-rate`) |
| `GET /api/v1/bo/resellers/stats/` | Totals, invited clients, pending applications and the top reseller over `RESELLERS.ranking_days` |
| `GET · PATCH /api/v1/bo/resellers/<id>/` | Detail; change `commission_rate` or `manager_id` |
| `POST /api/v1/bo/resellers/<id>/activate/` · `deactivate/` | Toggle access |
| `GET /api/v1/bo/resellers/<id>/invitees/` · `/api/v1/bo/me/invitees/` | Invited clients with order count and total; `meta.summary` has the code, count and overall total |
| `GET /api/v1/bo/me/referral/` | Code, invite link, QR code, share text and WhatsApp link |

Permissions:
- resellers: `referral.view.own`;
- managers: `resellers.view`, `resellers.manage`, `reseller_applications.review`.

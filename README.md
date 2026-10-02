# Celebobo API

Django REST + Channels backend for Celebobo. The architecture, the data model and the endpoint plan are in [`docs/BACKEND_PLAN.md`](docs/BACKEND_PLAN.md).

## Setup

```bash
uv sync
cp .env.example .env
docker run -d --name celebobo-pg -e POSTGRES_USER=celebobo -e POSTGRES_PASSWORD=celebobo -e POSTGRES_DB=celebobo -p 5432:5432 postgres:16-alpine
uv run pytest            # the test suite needs PostgreSQL with pgvector (TEST_DATABASE_URL overrides the default)
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

**User administration** (`UserAdminFacade`; managers can read, only admins can change anything):
- Accounts created by an admin have no password. Their email is marked verified, and an invitation with a password setup link goes out in the background.
- Deactivating an account sets it offline and revokes its refresh tokens. The same `AccessService` is used for resellers. Admins can't deactivate their own account.
- Anonymized (deleted) accounts are hidden from the list.

| Endpoint | Purpose |
|---|---|
| `GET · POST /api/v1/bo/users/` | List (`role`, `search`, `active`, `meta.counts` per role) or create an account |
| `GET · PATCH /api/v1/bo/users/<id>/` | Detail with the inviter; edit name, email or phone |
| `POST /api/v1/bo/users/<id>/activate/` · `deactivate/` | Toggle access |
| `POST /api/v1/bo/users/<id>/send-password-reset/` | Email a password reset link (`202`) |

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

**Shipping zones**
- `ShippingZone` has a name, cities, a fee, an optional free-shipping threshold and a delivery estimate.
- The delivery city (normalised for case, accents and hyphens) picks the zone. An unlisted city falls back to the `is_default` zone, and a quote without a city uses the `ORDERS` settings.
- Migration `0003` seeds two zones: Kinshasa ($2.98, free from $199, 24–48 h) and Autres villes ($7.50, the default).
- Orders store the zone name with the fee.

**Coupons**
- A `Coupon` is a percentage (optionally capped) or a fixed amount. It can require a minimum subtotal, give free shipping, run between `starts_at` and `ends_at`, and limit uses in total or per user.
- Carts keep a coupon code and check it again on every view. A coupon that no longer applies shows up as `coupon_error` and stops discounting.
- Checkout locks the coupon row and records a `CouponRedemption`. Redemptions on cancelled orders don't count against the limits.
- The discount is stored on the order (`total = subtotal − discount + shipping_fee`, enforced by a check constraint). It isn't spread over the items, so sales converted from a discounted order keep the item prices unless staff override them.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/cart/?city=` | Cart with the zone's shipping for that city |
| `POST · DELETE /api/v1/cart/coupon/` | Apply (`{code}`) or remove the cart's coupon |
| `POST /api/v1/checkout/quote/` | Also takes `city` and `coupon_code`; coupon problems come back as `coupon_error` |
| `POST /api/v1/orders/` | Takes `coupon_code`; an invalid code is a `400 coupon_rejected` with `meta.reason` |
| `GET /api/v1/shipping/zones/` | Active zones |
| `/api/v1/bo/shipping-zones/` (+ `<id>/`) | Zone management (`shipping.manage`, managers) |
| `/api/v1/bo/coupons/` (+ `<id>/`) | Coupons with uses and total discount; `DELETE` deactivates (`coupons.manage`, managers) |

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
- dashboard (staff): `dashboard.updated` after each refresh of the analytics facts;
- documents (the requester): `job.completed` when an export, import or report finishes;
- contact (staff): `contact_message.created`;
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

### `apps.analytics`

Dashboard KPIs and analytics, read from the `analytics_sales_fact` materialized view. The view is created in migration `0001_sales_facts` and read through the unmanaged `SalesFact` model. It aggregates `sales_sale` per hour (in `TIME_ZONE`), product, category, seller and payment method:
- revenue is net of refunds;
- profit only counts sales with a known cost;
- returned sales count for nothing.

**Freshness**
- The view refreshes `CONCURRENTLY` in three ways:
  - every `ANALYTICS_REFRESH_SECONDS` (Celery beat, default 600 s);
  - shortly after any sale change (an inline handler takes a cache lock and schedules one refresh after `ANALYTICS.refresh_debounce_seconds`);
  - on demand with `FactsFacade.refresh()`.
- Each refresh publishes `SalesFactsRefreshed`, which pushes `dashboard.updated` to staff.
- The recent-sales and open-orders widgets read live data.

**Periods and scope**
- `period` is `7d`, `30d` (default), `90d`, `12m` or `ytd`; `date_from` and `date_to` set a custom range instead.
- Every KPI is compared with the previous window of the same length.
- Series are daily up to 92 days and monthly beyond, and every bucket is filled.
- Staff can filter by `seller_id`, `category_id` and `payment_method`. Resellers always get their own numbers, whatever `seller_id` they send.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/bo/dashboard/summary/` | Revenue, profit, sales, units and average basket with previous value and % change; margin rate, today's revenue, open orders |
| `GET /api/v1/bo/dashboard/revenue-series/` | Revenue, profit, sales count and average basket per day or month |
| `GET /api/v1/bo/dashboard/payment-split/` | Revenue and share per payment method |
| `GET /api/v1/bo/dashboard/top-products/` | `by=revenue\|units\|profit`, `limit` (default 5) |
| `GET /api/v1/bo/dashboard/recent-sales/` · `open-orders/` | Live widgets |
| `GET /api/v1/bo/analytics/categories/` | Revenue, profit, margin and share per category (staff) |
| `GET /api/v1/bo/analytics/peak-hours/` | ISO weekday × hour heatmap (staff) |
| `GET /api/v1/bo/analytics/sellers/` | Seller ranking with revenue share (staff) |
| `GET /api/v1/bo/analytics/slow-movers/` | In-stock products older than the window with no sales in it, with their last sale (staff) |

Permissions: `dashboard.view` for resellers, `analytics.view` for managers.

The analytics page uses the dashboard endpoints with filters; `revenue-series` also carries the average-basket series, and `categories` the margin by category.

### `apps.documents`

Exports, the CSV product import, PDF reports and invoices.

**Jobs**
- Exports, imports and reports run as background jobs. A request answers `202` with the job, and the handler for `JobRequested` runs it through `generator_registry`, a factory per `JobKind`.
- When a job finishes, its owner gets `job.completed`. `GET /jobs/<id>/` is the fallback when that event is missed.
- Files are written to the private `documents` storage (`DOCUMENTS_ROOT`, default `var/documents`) and only reach the owner through `GET /jobs/<id>/download/`.
- Jobs and their files are purged after `DOCUMENTS_RETENTION_DAYS` by the `documents.purge_jobs` beat task.
- Writers come from `writer_registry`:
  - CSV is UTF-8 with a BOM and `;`, with formula-like cells escaped;
  - XLSX uses openpyxl;
  - PDF uses WeasyPrint, which needs Pango on the host (CI installs it).
- Exports reuse the requester's scope, so a reseller only exports their own sales.

**Product import**
- The file is checked before the job is queued: UTF-8, `name`, `category` (slug) and `price` columns, and the row and size limits.
- Each row goes through `ProductAdminFacade`, so stock movements, events and search indexing still happen.
  - A row whose `slug` exists updates that product; any other row creates one.
  - `stock` sets the stock with an inventory movement.
- Errors are reported per row in the job summary, and `dry_run=true` only reports.
- The products export uses the same columns, so an exported file can be edited and imported back.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/bo/sales/export/` | `format`: `csv`, `xlsx` or `pdf`, plus the sales list filters |
| `POST /api/v1/bo/products/export/` | `csv` or `xlsx` (managers) |
| `POST /api/v1/bo/products/import/` | Multipart `file` and `dry_run` (managers) |
| `POST /api/v1/bo/analytics/export/` | PDF activity report with the analytics filters |
| `GET /api/v1/jobs/` · `<id>/` · `<id>/download/` | The requester's jobs, status and file |
| `GET /api/v1/me/orders/<number>/invoice/` | The client's invoice as a PDF |
| `GET /api/v1/bo/orders/<id>/invoice/` | Invoice for staff and the assigned reseller |

Invoices are rendered on request, and cancelled orders have none. In the Django admin, products and sales can be exported with django-import-export (export only, so changes keep going through the domain).

### `apps.audit`

An audit trail with two sources, kept for `AUDIT_RETENTION_DAYS` (default 365) and purged by the `audit.purge` beat task.

**Model changes (django-auditlog)**
- `AUDITLOG_INCLUDE_TRACKING_MODELS` lists the tracked models: users, categories, products, variants, reviews, orders, sales, payouts and reseller applications. Field diffs are stored as JSON.
- Passwords, timestamps and derived counters are left out.
- `AuditlogMiddleware` records the IP address. JWTs are only checked inside DRF, so `ActorAwareView` sends `core.api.signals.request_authenticated` once a user is authenticated, and `apps.audit.receivers` attaches that user to the current auditlog context. Core never imports the audit app.
- Changes made outside a request (Celery jobs, anonymous forms) have no actor.

**Domain events (observer)**
- A background handler subscribed to `DomainEvent` records every published event: type, actor and encoded payload. Recording is keyed on `event_id`, so retries don't duplicate entries.
- `AUDIT.ignored_events` skips noise such as the analytics refresh.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/bo/audit-logs/` | Changes (`actor_id`, `action`, `object_type` as `app.model`, `object_id`, `date` or `date_from`/`date_to`, `search`) |
| `GET /api/v1/bo/audit-logs/<id>/` | One change with its diff |
| `GET /api/v1/bo/audit-logs/events/` | Domain events (`event_type`, `actor_id`, dates); `meta.event_types` lists the recorded types |
| `GET /api/v1/bo/audit-logs/object-types/` | Tracked models for the filter dropdown |

Permission: `audit.view` (admins).

### `apps.assistant`

A shopping assistant grounded in the catalogue. It uses pgvector retrieval and Gemini function calling, and streams its replies over SSE.

**Providers**
- `ASSISTANT_PROVIDER` selects the chat model and the embedder from the `chat_models` and `embedders` registries.
  - `gemini` needs `GEMINI_API_KEY`. It uses `GEMINI_CHAT_MODEL` (default `gemini-2.5-flash`) and `GEMINI_EMBEDDING_MODEL` (default `gemini-embedding-001`, 768 dimensions).
  - `offline` needs no key and is used by tests and local development: hashing embeddings and an assistant that lists matching products.

**Retrieval**
- `ProductEmbedding` holds one vector per visible product (`vector(768)`, HNSW cosine index) plus the category, price, promotion and stock metadata used for filtering.
- Background handlers refresh it on `ProductChanged`, `ProductRemoved` and `CategoryChanged`. A content hash skips products whose text hasn't changed, and hidden products lose their vector.
- `POST /bo/embeddings/reindex/` rebuilds every vector in the background.
- The model gets one tool, `search_products(query, category, on_sale, max_price)`. It runs a semantic search, then returns cards from the catalogue, so prices and stock are always current.

**Conversations**
- Sessions are identified by an unguessable UUID, so visitors can chat without an account; signed-in users also get their history.
- The model sees the system prompt, a rolling summary and the last `memory_messages` messages. When a reply is saved, `AssistantReplied` triggers background follow-ups that tag the question with a sentiment and a topic, and refresh the summary.
- Each reply stores its token usage, cost (`input_cost_per_million` / `output_cost_per_million`), latency, tool calls and error code.
- Limits:
  - the `assistant` throttle (12/min per user or IP);
  - `ASSISTANT_DAILY_MESSAGES` per day (`503 assistant_quota_exceeded`);
  - 1,000 characters per question.

**Streaming**
- `POST .../messages/` validates the question and checks the quota first, so those failures come back as normal problem+json errors.
- It then answers with `text/event-stream`, through an async iterator served by uvicorn. The events are:
  - `delta` (`{text}`);
  - `products` (the cards);
  - `done` (`{message_id, session_id, usage}`);
  - or `error` (`{code, detail}`) if the model fails mid-answer.
- `?stream=false` returns the same reply as one JSON object.

| Endpoint | Purpose |
|---|---|
| `GET · POST /api/v1/assistant/sessions/` | The signed-in user's conversations; start one (anyone) |
| `GET · DELETE /api/v1/assistant/sessions/<id>/` | History or deletion |
| `POST /api/v1/assistant/sessions/<id>/messages/` | Ask a question (SSE, or JSON with `?stream=false`) |
| `GET /api/v1/bo/assistant/logs/` | Questions with answer, sentiment, topic, tokens, cost and latency; `meta.stats` (managers) |
| `POST /api/v1/bo/embeddings/reindex/` | Rebuild product vectors (admins) |

The first migration creates the `vector` extension (`pgvector.django.VectorExtension`). Supabase and the `pgvector/pgvector` image both provide it.

### `apps.content`

The public site content and its back-office editors.

**Home and site content**
- `GET /home/` assembles the live banners (active and within `starts_at`/`ends_at`), deals, new arrivals, best sellers, and the best sellers of the first four categories. Products come from the catalogue through the `Showcase` port, so favourites and caching still apply.
- `SiteSettings` is a single row:
  - exchange rate (`usd_to_cdf`), hotline, WhatsApp, e-mail, address;
  - opening hours, enabled payment methods (checked against `PaymentMethod`), social links;
  - the newsletter welcome code.
- Public settings add the shipping rules from `ORDERS` (read-only) and never expose the newsletter code.
- Pages, the FAQ and public settings are cached in `ContentCache`. Any `SiteContentChanged` or `CategoryChanged` bumps its version.
- Pages, the FAQ and banners share one generic `Editor` service, with validators for unique slugs and banner schedules. The back-office endpoints come from a single `editor_viewset` factory.

**Contact and newsletter**
- The contact form is throttled to 5 per hour. A hidden `website` field catches bots: those messages are filed as `spam` and send nothing.
- Every real message emails an acknowledgement to the sender and an alert to the site e-mail, in the background, and pushes `contact_message.created` to staff.
- The newsletter is throttled to 10 per hour. Subscribing returns the welcome code and emails it with an unsubscribe link (`FRONTEND_URL/newsletter/desinscription?token=…`). Subscribing again is idempotent, and an unsubscribed address can come back.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/home/` | Home sections |
| `GET /api/v1/settings/public/` | Exchange rate, contacts, hours, payment methods, social links, shipping rules |
| `GET /api/v1/pages/` · `pages/<slug>/` · `faq/` | Published pages and the FAQ grouped by category |
| `POST /api/v1/contact/` | Contact form (`202`) |
| `POST /api/v1/newsletter/subscribe/` · `unsubscribe/` | Newsletter |
| `GET · PATCH /api/v1/bo/settings/` | Site settings (admins) |
| `GET /api/v1/bo/contact-messages/` · `GET · PATCH <id>/` | Inbox with `meta.counts`; set `status` (new, handled, spam) and an internal `note` |
| `GET /api/v1/bo/newsletter/subscribers/` · `export/` | Subscribers (`active`, `search`) and a CSV export |
| `/api/v1/bo/pages/` · `bo/faq/` · `bo/banners/` (+ `<id>/`) | Content editors (managers) |

Permissions:
- managers: `contact.inbox`, `newsletter.view`, `content.manage`;
- admins: `settings.manage`.

### `apps.push`

Browser push notifications (Web Push with VAPID), the third notification channel next to `in_app` and `email`.

**Devices**
- The frontend reads `GET /push/public-key/`, subscribes through the browser's Push API and sends the subscription to `POST /me/devices/`.
- The endpoint must be HTTPS and is unique: a browser that signs in to another account moves to that account.
- Each user can register up to `PUSH.max_devices` devices (10).

**Delivery**
- Messaging's `push` notifier sends each notification to recipients whose preferences allow push for that topic (`order_assigned`, `status_changed` and `new_message` are on by default, `promotions` is off).
- `PushDispatcher` uses the `PushSender` contract (pywebpush adapter). Subscriptions the push service reports as gone (404/410) are deleted. Other failures are counted, and a device is dropped after `max_failures` (5) failed sends.
- Nothing is sent until `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` are set.
  - `uv run vapid --gen` writes `private_key.pem` and `public_key.pem`.
  - `uv run vapid --applicationServerKey` prints the public key to use as `VAPID_PUBLIC_KEY`.
  - `VAPID_PRIVATE_KEY` is the path to `private_key.pem`, or the key itself in base64 DER form.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/push/public-key/` | VAPID public key and whether push is enabled |
| `GET · POST /api/v1/me/devices/` | The user's devices; register `{endpoint, keys: {p256dh, auth}, user_agent}` |
| `DELETE /api/v1/me/devices/<id>/` | Remove a device |

## Security hardening

**Login lockout (django-axes)**
- `AXES_FAILURE_LIMIT` failed logins (5) for the same email from the same IP lock that pair for `AXES_COOLOFF_MINUTES` (15).
- The JSON login answers `429 too_many_login_attempts`; the Django admin login is covered too.
- `LockoutAwareLoginSerializer` reads the lockout flag that axes sets on the DRF request. It also sends `user_logged_in` on success, so the counter resets and `last_login` is updated, which dj-rest-auth skips when session login is off.
- Behind a proxy, set `AXES_PROXY_COUNT` so the client IP is read from `X-Forwarded-For`.

**Headers and rate limits**
- django-csp sends a strict `Content-Security-Policy`:
  - `default-src 'self'`, no plugins, `frame-ancestors 'none'`;
  - images also from Cloudinary.
  - The Swagger and ReDoc pages are excluded because they load assets from a CDN.
- Production already sets HSTS, secure cookies, `nosniff`, `DENY` framing and a strict referrer policy.
- Scoped throttles cover authentication (`auth`, `dj_rest_auth`), referral checks, tracking, uploads, the assistant, contact, the newsletter, reseller applications and coupon attempts (`coupons`, 20/hour).

**Media**
- Avatars are set with `avatar_upload_id`. The upload must be an avatar uploaded by the same user, so arbitrary URLs can no longer be stored.
- The daily `media.sweep_orphans` task deletes Cloudinary uploads older than 24 h that nothing references any more, using a signed `destroy` call.
- Apps say what they still reference through the `media_references` registry: catalog images, avatars, banners and message attachments.

**API contract tests**
- `config/tests/test_api_contract.py` runs Schemathesis against the generated OpenAPI schema. It fuzzes every GET operation anonymously and every back-office GET as an admin.
- It fails on any 5xx and on any response that doesn't match its documented schema. Paginated endpoints document their envelope with `core.api.pagination.page_of`.

## Deployment

**Single container (Koyeb)**
- The root `Dockerfile` and `entrypoint.sh` run everything in one container:
  - migrations (skipped with `RUN_MIGRATIONS=false`);
  - a Celery worker on all queues (`CELERY_CONCURRENCY`, default 1);
  - Celery beat;
  - Gunicorn with Uvicorn workers on `config.asgi` (`WEB_CONCURRENCY`, default 1), so WebSockets and SSE work.
- `Procfile`, `runtime.txt` and `.python-version` cover buildpack builds, but the Docker builder is preferred: WeasyPrint needs Pango from the system.
- Use a TCP health check, or HTTP on `/health/live/` only if the probe sends a `Host` header that is listed in `DJANGO_ALLOWED_HOSTS`.

**Multi-container production:** see `deploy-real-prod/README.md`. It covers the separate API, `default`/`ai`/`exports` workers, beat and a migration job, plus an optional local Postgres/pgbouncer/Redis stack.

# Celebobo v2 — Backend plan (DRF + Channels)

Sources:
- the old project `../shopproject` (pure Django);
- the UI mock-up `cele-bobo.vercel.app` (+ `/admin`);
- your ~170 endpoints.

**The backend owns the API contract.** The UI is used only for features, fields, enums and workflows. §11 lists what the UI will need to adapt.

---

## 0. Principles

- **Layers go one way only:** `api → facades → services → repositories/selectors → models`. Infrastructure adapters implement contracts and are injected; nothing imports them directly.
- **Views are transport only.** They validate the input, build a command, call one facade method, and serialise the result.
- **Services depend on contracts (`Protocol`s), not on implementations.** Factories build the implementation chosen in settings, so tests swap in fakes without monkeypatching.
- **Side effects are events.** A use case publishes a domain event. Observers handle the rest: notifications, WebSocket, audit, search index, aggregates, metrics.
- **Apps talk to each other only through facades or contracts.** One app never touches another app's models. `import-linter` enforces this in CI.
- **Code is self-documenting:** explicit names, small functions, typed DTOs, no comments by default.
- **The API is versioned (`api/v1/`, `api/v2/`).** Facades and services are version-agnostic; only the `api/vN` packages change.

---

## 1. Architecture

### 1.1 Layers

| Layer | Contents | Can import |
|---|---|---|
| `api/v1/` | ViewSets, input/output serializers, URL routes, filtersets | facades, DTOs, core.api |
| `facades.py` | One facade per bounded context. It orchestrates services inside one transaction and publishes events. | services (through contracts), events, DTOs |
| `services/` | Business rules: pricing, stock, the order state machine, commission calculation… | contracts, repositories, selectors, domain |
| `contracts.py` | `Protocol`s for services and adapters | domain, DTOs |
| `repositories.py` / `selectors.py` | Writes on aggregates (with locking) / optimised reads (querysets, annotations) | models |
| `domain/` | DTOs (`@dataclass(frozen=True, slots=True)`), enums, value objects (`Money`), `DomainError`s, events | stdlib only |
| `adapters/` | Cloudinary, Gemini, PostgreSQL full-text search, SMTP/SES, WebPush, WeasyPrint, openpyxl | contracts, third-party SDKs |
| `handlers.py` | Observers subscribed to events | facades/services of their own app, celery tasks |
| `tasks.py` | Celery entry points. Thin: they resolve a facade and call it. | facades |

### 1.2 Contracts

```python
class StockService(Protocol):
    def reserve(self, lines: Sequence[StockLine], *, reason: StockReason, source: SourceRef) -> None: ...
    def release(self, lines: Sequence[StockLine], *, reason: StockReason, source: SourceRef) -> None: ...
    def adjust(self, command: AdjustStock, actor: Actor) -> StockMovementDTO: ...


class MediaStorage(Protocol):
    def upload(self, file: BinaryIO, *, folder: str, transformation: ImageProfile) -> StoredMedia: ...
    def sign_upload(self, *, folder: str, profile: ImageProfile) -> UploadSignature: ...
    def delete(self, public_id: str) -> None: ...


class LLMClient(Protocol):
    def stream(self, prompt: Prompt) -> AsyncIterator[LLMChunk]: ...
    def embed(self, texts: Sequence[str]) -> list[Vector]: ...


class SearchEngine(Protocol):
    def search(self, query: ProductQuery) -> SearchPage: ...
    def suggest(self, text: str, *, limit: int) -> list[Suggestion]: ...
    def index(self, documents: Sequence[ProductDocument]) -> None: ...
    def remove(self, ids: Sequence[int]) -> None: ...


class Exporter(Protocol):
    media_type: str
    extension: str
    def render(self, dataset: Dataset) -> bytes | Iterator[bytes]: ...


class Notifier(Protocol):
    channel: NotificationChannel
    def send(self, notification: OutboundNotification) -> None: ...
```

### 1.3 Factories

There is one generic registry, used by every factory. Implementations are selected from settings, so swapping a provider is a configuration change.

```python
class Registry(Generic[T]):
    def __init__(self, contract: type[T]) -> None:
        self._contract = contract
        self._builders: dict[str, Callable[[], T]] = {}

    def register(self, key: str) -> Callable[[Callable[[], T]], Callable[[], T]]:
        def decorator(builder: Callable[[], T]) -> Callable[[], T]:
            self._builders[key] = builder
            return builder
        return decorator

    def create(self, key: str) -> T:
        try:
            return self._builders[key]()
        except KeyError as exc:
            raise ImproperlyConfigured(f"{self._contract.__name__}: unknown provider '{key}'") from exc


storage_registry = Registry(MediaStorage)
search_registry = Registry(SearchEngine)
exporter_registry = Registry(Exporter)
notifier_registry = Registry(Notifier)
llm_registry = Registry(LLMClient)


@exporter_registry.register("xlsx")
def _xlsx() -> Exporter:
    return XlsxExporter()
```

```python
class ServiceFactory:
    @cached_property
    def storage(self) -> MediaStorage:
        return storage_registry.create(settings.PROVIDERS["storage"])

    @cached_property
    def search(self) -> SearchEngine:
        return FallbackSearch(
            primary=search_registry.create("postgres"),
            fallback=search_registry.create("postgres"),
        )

    def exporter(self, fmt: ExportFormat) -> Exporter:
        return exporter_registry.create(fmt.value)

    def notifiers(self, channels: Iterable[NotificationChannel]) -> list[Notifier]:
        return [notifier_registry.create(c.value) for c in channels]


class FacadeFactory:
    def __init__(self, services: ServiceFactory, bus: EventBus) -> None:
        self._services = services
        self._bus = bus

    def checkout(self) -> CheckoutFacade:
        return CheckoutFacade(
            pricing=PricingService(settings_provider=SiteSettingsSelector()),
            stock=DefaultStockService(StockRepository()),
            orders=OrderRepository(),
            conversations=ConversationService(ConversationRepository()),
            idempotency=IdempotencyStore(cache),
            bus=self._bus,
        )
```

`core/container.py` exposes a process-wide `container = FacadeFactory(ServiceFactory(), event_bus)` and an `override()` context manager for tests.

The same factory approach covers:
- **order transitions**: a `TransitionPolicyFactory` per role;
- **paginators**: a `PaginationFactory` returning cursor or page-number pagination per view;
- **dashboard scope**: a `DashboardScopeFactory` that returns the global scope or the reseller's own.

### 1.4 Facade + logging decorator

`core/observability.py` provides two decorators:
- `@use_case` on a method;
- `@logged_facade` on a class, which applies `@use_case` to every public method.

```python
def use_case(fn: Callable[P, R]) -> Callable[P, R]:
    operation = fn.__qualname__

    @wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        log = structlog.get_logger().bind(use_case=operation)
        started = perf_counter()
        try:
            result = fn(*args, **kwargs)
        except DomainError as exc:
            log.warning("use_case.rejected", code=exc.code, duration_ms=_elapsed(started))
            metrics.increment("use_case.rejected", tags={"use_case": operation, "code": exc.code})
            raise
        except Exception:
            log.exception("use_case.failed", duration_ms=_elapsed(started))
            metrics.increment("use_case.failed", tags={"use_case": operation})
            raise
        log.info("use_case.completed", duration_ms=_elapsed(started))
        metrics.timing("use_case.duration", _elapsed(started), tags={"use_case": operation})
        return result

    return wrapper


def logged_facade(cls: type[T]) -> type[T]:
    for name, member in list(vars(cls).items()):
        if callable(member) and not name.startswith("_"):
            setattr(cls, name, use_case(member))
    return cls
```

```python
@logged_facade
class CheckoutFacade:
    def __init__(self, *, pricing: PricingPolicy, stock: StockService, orders: OrderRepository,
                 conversations: ConversationService, idempotency: IdempotencyStore, bus: EventBus) -> None:
        ...

    def place_order(self, command: PlaceOrder, actor: Actor) -> PlacedOrder:
        with self._idempotency.guard(command.idempotency_key, actor) as cached:
            if cached:
                return cached
            with transaction.atomic():
                quote = self._pricing.quote(command.lines, command.shipping_zone)
                self._stock.reserve(quote.stock_lines, reason=StockReason.ORDER, source=SourceRef.pending())
                order = self._orders.create(command, quote, actor)
                conversation = self._conversations.open_for_order(order)
                self._bus.publish(OrderCreated.from_order(order, conversation_id=conversation.id))
            return PlacedOrder(order=OrderDTO.from_model(order), conversation_id=conversation.id)
```

`structlog` context (`request_id`, `user_id`, `role`, `api_version`) is bound once by middleware and carried into Celery tasks through task headers. Every log line from a use case is therefore correlated with its request.

### 1.5 Observer: the event bus

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=timezone.now)
    actor_id: int | None = None


class EventBus:
    def __init__(self, dispatcher: AsyncDispatcher) -> None:
        self._sync: defaultdict[type[DomainEvent], list[Handler]] = defaultdict(list)
        self._async: defaultdict[type[DomainEvent], list[str]] = defaultdict(list)
        self._dispatcher = dispatcher

    def on(self, *event_types: type[DomainEvent], background: bool = False) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            for event_type in event_types:
                if background:
                    self._async[event_type].append(dotted_path(handler))
                else:
                    self._sync[event_type].append(handler)
            return handler
        return decorator

    def publish(self, event: DomainEvent) -> None:
        transaction.on_commit(lambda: self._dispatch(event))

    def _dispatch(self, event: DomainEvent) -> None:
        for event_type in type(event).__mro__:
            for handler in self._sync.get(event_type, ()):
                self._safely(handler, event)
            for path in self._async.get(event_type, ()):
                self._dispatcher.enqueue(path, event)
```

**How it works:**
- `publish` runs only after the transaction commits, so a rollback never sends a notification.
- A handler that fails is logged and isolated; it never breaks the use case.
- Background handlers run in Celery through a single `dispatch_event` task. It serialises the event with `dataclasses.asdict` and an idempotency key `event_id:handler`.

**Global observers** subscribe to `DomainEvent`, so they receive every event:
- `AuditObserver`
- `MetricsObserver`
- `RealtimeObserver` (maps events to WebSocket groups)

**Domain observers:**

| Event | Observers |
|---|---|
| `OrderCreated` | Notify managers · WS `order.created` |
| `OrderAssigned` | WS for the reseller + client · notify the reseller · email |
| `OrderStatusChanged` | Timeline · WS · close the conversation on a final status · release stock if cancelled · commission on `livree` |
| `SaleRecorded` | Update aggregates · commission ledger · WS `sale.created` · `stock.low` check |
| `SaleRefunded` | Reverse aggregates and commission · restock if it's a return |
| `ProductChanged` | Refresh `search_vector` · re-embed · invalidate cache |
| `MessagePosted` | WS · unread counts · offline notification (email/push) |
| `PriceProposalAnswered` | Recompute the order total · WS `order.updated` |
| `ResellerApplicationSubmitted` | Notify staff · email acknowledgement |
| `ExportRequested` / `ExportCompleted` | Celery job · WS `job.completed` |
| `UserDeactivated` / `PasswordChanged` | Revoke sessions · WS `session.revoked` |

Handlers live in each app's `handlers.py`. They are imported in `AppConfig.ready()`. **Django model signals are not used for business logic**; at most, one generic `post_save` → `ProductChanged` bridge for edits made in Django admin.

### 1.6 Thin views

```python
class OrderViewSet(UseCaseViewSet):
    permission_classes = [HasPerm("orders.create")]
    facade = container.checkout

    @extend_schema(request=PlaceOrderInput, responses={201: PlacedOrderOutput})
    def create(self, request: Request) -> Response:
        command = self.parse(PlaceOrderInput, request, idempotency_key=request.idempotency_key)
        result = self.facade().place_order(command, actor=request.actor)
        return self.respond(PlacedOrderOutput, result, status=201)
```

`core.api.UseCaseViewSet` provides `parse()` (input serializer → frozen DTO), `respond()`, `request.actor` (built by middleware), and the pagination/filter factory. All read endpoints use `SelectorViewSet` with `selector`, `filterset_class` and `output_serializer`; they contain no business code.

**Errors:** `DomainError` is subclassed into `NotFound`, `Conflict`, `Forbidden`, `InvalidTransition`, `InsufficientStock` and `BusinessRuleViolation`. One exception handler maps them to `problem+json`, with a stable `code`, a French `detail` and `errors{field:[...]}`.

### 1.7 Testability

- **Domain and services:** pure unit tests with in-memory fakes that implement the contracts (`FakeStorage`, `FakeSearch`, `FakeLLM`, `RecordingBus`), no DB.
- **Facades:** `pytest-django` + `factory_boy`, with `container.override(...)`. Assert on the events published, not on side effects.
- **Contract tests:** one parametrised suite per `Protocol`, run against every adapter (Cloudinary is mocked; full-text search runs on the CI Postgres service).
- **API:** `APIClient` tests per endpoint for permissions × roles (a matrix test generated from `permissions.py`), plus Schemathesis on `/schema/`.
- **Guards:** `import-linter` (layers and app independence), `mypy --strict` with django-stubs/drf-stubs, a coverage gate on `services/` and `domain/`.

---

## 2. Project layout

```
config/
  settings/{base,dev,test,prod}.py
  asgi.py  wsgi.py  celery.py  urls.py
core/
  api/            UseCaseViewSet, SelectorViewSet, pagination factory, exception handler, versioning, idempotency
  observability/  use_case, logged_facade, structlog config, request_id middleware, metrics
  events/         DomainEvent, EventBus, dispatch_event task
  container.py    ServiceFactory, FacadeFactory, override()
  registry.py     Registry[T]
  permissions.py  rules predicates + permission matrix + HasPerm
  domain/         Money, Actor, Page, base errors
apps/
  accounts/       User, Address, Preferences, Push, ResellerApplication
  catalog/        Category, Product, Variant, Image, Review, Favorite, StockMovement
  search/         SearchEngine adapter (PostgreSQL full-text), indexer
  orders/         Cart, Order, OrderItem, StatusEvent, PriceProposal, state machine
  messaging/      Conversation, Participant, Message, Notification, consumers
  sales/          Sale, Refund, CommissionLedger, Payout
  analytics/      aggregate tables, dashboard selectors, exports
  media/          MediaStorage adapters, upload signing
  assistant/      LLMClient adapters, RAG, SSE view, analytics
  cms/            HomeContent, SiteSettings, Pages, FAQ, Contact, Newsletter
  audit/          auditlog integration, AuditObserver, audit API
```

Each app follows the same layout:

```
apps/orders/
  domain/{dtos,enums,events,errors}.py
  contracts.py
  services/{pricing,state_machine,assignment,price_proposals}.py
  repositories.py
  selectors.py
  facades.py
  handlers.py
  tasks.py
  adapters/
  api/v1/{serializers,views,filters,urls}.py
  admin.py
  models.py
  tests/{unit,integration,api,factories.py,fakes.py}
```

---

## 3. Data model (Postgres on Supabase)

Use a **custom User model from day 1**; the old project used `auth.User` + `Profile`. Enum values below are the UI's French labels; the API stores English values (see §4.3) and the UI maps them to labels.

### `accounts`
- **User**(AbstractUser):
  - identity and contact: `email` (unique, login), `phone_number` (unique, null), `avatar` (Cloudinary);
  - `role` (`client|revendeur|mukubwa|admin`, indexed; synced to a Group of the same name);
  - referral: `code_revendeur` (char 4, **unique**, null, digits only), `invited_by` → User (SET_NULL);
  - reseller fields: `availability` (`online|away|offline`), `commission_rate` (Decimal 4,3, default 0.070, CHECK 0–0.5), `manager` → User (null);
  - `last_seen_at`;
  - profile addresses as JSON or embedded columns: `delivery_address{line1, line2, country}`, `billing_address`, `same_as_delivery`.
- **Address**: `user`, `label` (Domicile|Bureau|Famille|Autre), `recipient`, `phone`, `line1`, `quarter`, `city`, `country`, `is_default`.
  - `UniqueConstraint(user, condition=is_default)` so each user has only one default.
- **NotificationPreference**: `user` (1-1), with `order_assigned`, `status_changed`, `new_message`, `promotions` each `{email, push}`. Use a JSONField or 8 booleans.
- **PushSubscription**: `user`, `endpoint`, `p256dh`, `auth`, `user_agent`. VAPID isn't set up on the UI yet.
- **ResellerApplication**:
  - `reference` ("REV-2026-201"), `full_name`, `phone`, `email`, `city`, `motivation`, `referral_code`;
  - `status` (new/approved/rejected), `reviewed_by`, `reviewed_at`.

### `catalog`
- **Category**:
  - `name` (unique, case-insensitive: `UniqueConstraint(Lower("name"))`), `slug`, `description`, `image`;
  - `icon` (enum of 10 values), `active`, `order` (position);
  - safedelete.
- **Product**:
  - text: `name`, `slug`, `description` (keep the 20–100 character + verb validator, with the same French message), `long_description` (≤ 5 sentences);
  - pricing: `price`, `price_solde` (null, CHECK `< price`), `price_primary` (cost; **never serialised to clients**). Compute `solde_percent` in the serializer or store it as a `GeneratedField`;
  - `category` → Category (PROTECT);
  - badges: `badge` (null | Nouveauté | Best-seller); `current_badge` is computed;
  - care and delivery text: `chara_entretien`, `delivery_policy_phase1`, `delivery_policy_phase2`, `free_shipping`, `shipping_fee`;
  - stock: `stock` (used when there are no variants), `stock_threshold` (5), `date_wish`;
  - lifecycle: `is_active`, `date_added`;
  - denormalised counters `rating_avg`, `reviews_count`, `sales_count`, updated by signals or Celery. They remove the old N+1 queries;
  - **safedelete** (`deleted_at`) drives the trash/restore actions the UI already has;
  - `search_vector` (`SearchVectorField` + GIN index) for PostgreSQL full-text search.
- **ProductImage**: `product`, `image`, `position` (0–3).
  - The serializer exposes `image` and `images[]` and accepts the 4 multipart slot fields.
- **ProductFeature**: `product`, `name`, `position`.
- **ProductOption** (`name`, e.g. "Couleur") and **ProductOptionValue**: these produce `variant_options`.
- **ProductVariant**: `product`, `sku` (unique), `attributes` (JSONB, e.g. `{Couleur:"Noir", Stockage:"256 Go"}`), `label`, `price` (null = use the product price), `stock`, `image`.
  - `UniqueConstraint(product, attributes)`.
  - The product's `in_stock`/`stock` is the sum of its variants' stock.
- **StockMovement**: `product`, `variant` (null), `delta`, `balance_after`, `reason` (inventaire|vente|réapprovisionnement|correction|perte|retour), `note`, `by`, `at`, plus a generic `source` (order or sale id).
  - **Append-only**: no update and no delete.
- **Review** (the API calls it `testimonies`): `product`, `user`, `rating` (CHECK 1–5), `message` (10–2000 characters), `verified`, `status` (for moderation), `created_at`.
  - `UniqueConstraint(product, user)`. The old project enforced this only in the view.
- **Favorite**: `user`, `product`, `created_at`, `UniqueConstraint`.
- **ProductEmbedding / CategoryEmbedding**: reuse the old ones (pgvector 768, HNSW cosine).

### `orders`
- **Cart / CartItem**: `owner` (user or anonymous token), `product`, `variant`, `quantity`.
- **Order**:
  - `number` (public, unguessable — `/suivi` uses it), `user`, `status` (pending|assigned|confirmed|paid|shipping|delivered|cancelled|returned);
  - `assigned_reseller` → User (null);
  - **snapshot of the delivery address**: `recipient`, `phone`, `line1`, `quarter`, `city`, `country`;
  - `payment_method` (OrangeMoney|AirtelMoney|M-Pesa|Cash), `note`;
  - amounts: `subtotal`, `shipping_fee`, `total_price`;
  - `cancel_reason`, `converted_to_sales_at`, `idempotency_key` (unique, null).
  - Use a **state machine** (django-fsm-2 or your own transitions table) that follows §4.3:
    - client: attente → annulee;
    - reseller: one step forward;
    - mukubwa/admin: any forward step, or annulee;
    - livree → retournee.
- **OrderItem**: `order`, `product` (SET_NULL), `variant` (SET_NULL), snapshots `product_name`, `product_image`, `variant_label`, then `quantity` and `unit_price`.
- **OrderStatusEvent**: `order`, `from_status`, `to_status`, `by` (with role), `note`, `reason`, `at`. This produces `statusHistory`.
- **PriceProposal**: `order_item`, `message` (1-1), `old_price`, `new_price`, `reason`, `status` (pending|accepted|refused), `proposed_by`, `responded_at`.
  - **This is missing from your list**; see §4.
- **Coupon**: optional. The newsletter returns `BIENVENUE10`, but **checkout has no coupon field**, so it is pointless until the UI adds one.

### `messaging`
- **Conversation**:
  - `kind` (order|support), `order` (1-1, null), `client`, `assigned_reseller`, `participants` (M2M through **Participant**);
  - `concluded`/`closed_at`, `last_message_at`;
  - denormalised `last_message` for the conversation list.
- **Participant**: `conversation`, `user`, `role`, `last_read_message` (FK). This gives `unreadCount` without a per-message "seen" table.
- **Message**: `conversation`, `sender` (null = the system pseudo-user), `content`, `image`, `metadata` (JSONB: system | generatedFromCart | price_proposal), `client_msg_id` (unique per sender), `created_at`.
- **Notification**:
  - `recipient` (one row per manager, instead of the UI's `userId=0` broadcast), `type` (order|chat), `title`, `body`;
  - `conversation` (null), `order` (null), `is_read`, `is_order_assigned`, `created_at`.

### `sales`
- **Sale**:
  - `product`, `variant`, `seller` → User, `buyer` (null), `sold_to` (free text);
  - `quantity`, `unit_price`, `unit_cost` (**snapshot of `price_primary`** at the time of the sale, so profit stays correct when the cost changes);
  - `method`, `sold_at` (**editable**; the old code used `auto_now_add`, which ignored the date entered), `recorded_at`;
  - `order` (null), `order_item` (null, **unique** → converting an order twice can't duplicate sales);
  - `status` (valide|remboursée|retournée).
- **Refund**: `sale`, `type` (remboursement|retour), `amount`, `reason`, `by`, `at`. A *retour* creates a StockMovement (+qty).
- **CommissionPayment**: `reseller`, `amount`, `paid_at`, `note`, `paid_by`.
- **CommissionLedger** (recommended): one row per sale with `rate` and `amount` **frozen at the time of the sale**. Without it, changing a reseller's rate rewrites their history.

### `cms` / `core`
- **HomeContent**: a versioned JSON singleton with `slides`, `miniBanners`, `promoCards`, `brands`, `sideBanners`, `editorial`, `showcases`, `columns`, `dealEndsAt`, `seo`. Edit it in Django admin; it doesn't need a full banners/sections CRUD in v1.
- **SiteSettings** singleton: free-shipping threshold (199), delivery zones, payment methods, hotline, opening hours, WhatsApp link, warranty and return periods.
- **ContactMessage** (`reference` CT-2026-xxxx, status), **NewsletterSubscriber**.
- **AuditLog**: from **django-auditlog**. It already stores the actor, the object and a `changes` diff, which match the UI's `diff[{field,from,to}]`. Add a French label per action.
- **ChatLog / ProductQuestion**: the assistant analytics from the old project (sentiment, language). Reuse them.

**django-simple-history or django-auditlog?** Pick **auditlog**: the UI needs one global log with diffs. Don't use simple-history for order status; `OrderStatusEvent` is a domain table.

---


---

## 4. API

### 4.1 Cross-cutting decisions

| Topic | Decision |
|---|---|
| Versioning | `NamespaceVersioning`: `/api/v1/` is mounted as the `v1` namespace, so views never receive a `version` kwarg. Every app has `api/v1/urls.py`; `core/api/routing.py` discovers and mounts them for each entry in `ALLOWED_VERSIONS`. |
| Auth | dj-rest-auth + allauth with **JWT in httpOnly cookies** (`JWT_AUTH_COOKIE`, `JWT_AUTH_REFRESH_COOKIE`, rotation + blacklist). This works for SSR (Next.js server components forward the cookie) and for a future mobile app (it sends a Bearer header instead). |
| Domains | `celebobo.com` + `api.celebobo.com`, so cookies are same-site (`SameSite=Lax`, `Domain=.celebobo.com`). `*.vercel.app` → API on another domain is cross-site and Safari will drop the cookies. |
| WebSocket auth | `POST /auth/ws-ticket/` → a single-use ticket, kept 30 s in Redis, passed as `wss://api…/ws/?ticket=`. Independent of cookies. |
| Pagination | `PaginationFactory`: **cursor** for feeds (messages, notifications, audit, stock movements, sales feed, storefront infinite scroll); **page-number** for admin tables with totals (products, orders, users, resellers). Both return `{results, next, previous, meta}`, where `meta` holds `count`/`stats` when they apply. |
| Errors | `application/problem+json`: `{type, title, status, code, detail, errors}`. |
| Idempotency | `Idempotency-Key` header on order creation, sales, refunds, payouts, conversion. The response is kept 24 h in Redis, and a different body with the same key → 422. |
| Casing | snake_case in JSON (the UI converts it). |
| Long jobs | 202 `{job_id}` → WS `job.completed` + `GET /jobs/{id}/`. |
| Uploads | `POST /uploads/sign/` → Cloudinary signed params (folder, eager transformations, chunk size) → direct browser upload → `POST /uploads/complete/ {public_id, purpose}` → an `UploadedMedia` row that the entity referencing it then claims. Product, avatar and chat images all go through this. |

### 4.2 Your list, amended

Your endpoint list stays the base. The UI adds the following requirements.

**Add:**
1. `POST /conversations/{id}/price-proposals/` and `POST /price-proposals/{id}/respond/ {accept}`.
   - Requires `price.adjust`. Only the client responds, and only once (409 otherwise).
   - Accepting a proposal updates `OrderItem.unit_price` and the order total, and is allowed only before `payee`.
2. `POST /bo/orders/{id}/assignment/accept/` · `/decline/ {reason}` (reseller).
   - Declining sends the order back to `attente`, with no reseller assigned, and notifies staff.
   - Do the same for support conversations: `/conversations/{id}/assignment/accept|decline/`.
3. `GET /bo/orders/convertible/?search=`: orders that can be turned into sales, with `blocked_reason` for those that can't.
4. `DELETE /bo/categories/{id}/?move_to=`: 409 `{code:"category_not_empty", products_count}` when the category still has products and no target is given.
5. `GET /products/{slug}/reviews/eligibility/` → `{can_review, reason}`.
6. `GET /bo/me/dashboard/`: the reseller's own dashboard in one call. You can also reuse `/bo/dashboard/*` with the reseller scope (via `DashboardScopeFactory`). Pick one.
7. `GET /bo/products/{id}/stats/` (units, revenue, profit) and `POST /bo/variants/{id}/stock-adjustments/ {mode: delta|set}`.
8. `GET /bo/analytics/slow-movers/` (no sale in 45 days, ≤1 unit in 60 days, or `date_wish` ≤ 14 days away) · `/stock-value-series/` · `/assistant/` (questions, sentiment, cost).
9. `GET /bo/me/permissions/`, or put `permissions[]` in `/me/`, so the UI stops hard-coding the matrix.
10. `GET /shipping/zones/` + delivery fee in `/cart/`.
    - The UI's guide has these zones: Kinshasa 24–48 h, free from $199, otherwise $2.98; other cities from $7.50.
11. `POST /bo/search/reindex/` · `/bo/embeddings/reindex/` (jobs, admin only).

**Change:**
- **Returns:** `POST /bo/sales/{id}/refund/` and the order transition `→ returned` both go through `RefundService`. That one service creates the refund, the stock movement and the reversal of the commission.
- **Invoice:** add `GET /me/orders/{id}/invoice/` for the client. Keep `/bo/orders/{id}/invoice/` for staff.
- **Coupons:** the `/newsletter/subscribe/` response promises a 10% code, so add `POST/DELETE /cart/coupon/` + `CRUD /bo/coupons/`, or drop the promise.

**Defer** (not in the UI; Django admin covers them in v1):
- banners, home sections, brands, pages, FAQ: edited through `HomeContent`/`SiteSettings` in Django admin;
- sessions and devices;
- webhooks (mobile money, WhatsApp).

### 4.3 Order state machine

Use the UI's statuses, in English for the API:

`pending → assigned → confirmed → paid → shipping → delivered`, plus `cancelled` and `returned`.

| Role | Allowed |
|---|---|
| Client | `pending → cancelled` (own order) |
| Reseller | One step forward on orders assigned to them; accept/decline the assignment |
| Manager/Admin | Any forward step; `cancelled` from any non-final status; `delivered → returned` |

- `TransitionPolicyFactory.for_actor(actor)` returns the policy for that role.
- `OrderStateMachine.transition(order, to, actor, reason)` checks the policy, then:
  - writes an `OrderStatusEvent`;
  - publishes `OrderStatusChanged`;
  - returns `allowed_transitions` for the UI.

---

## 5. Permissions

Store the matrix from the UI (module 72352) in `core/permissions.py` as **django-rules predicates**. Each role includes every permission of the role below it.

- **revendeur:** `backoffice.access`, `dashboard.own`, `orders.view.own`, `orders.status.advance`, `sales.view.own`, `sales.create`, `sales.convert`, `sales.edit.own`, `products.view`, `commissions.view.own`, `inbox.view.own`, `price.adjust`.
- **mukubwa adds:** `dashboard.all`, `orders.view.all`, `orders.assign`, `orders.status.any`, `orders.cancel`, `sales.view.all`, `sales.edit.all`, `sales.refund`, `sales.export`, `products.manage`, `products.import`, `stock.adjust`, `categories.manage`, `resellers.view`, `resellers.manage`, `commissions.view.all`, `analytics.view`, `analytics.resellers`, `inbox.view.all`.
- **admin adds:** `sales.delete`, `products.delete`, `commissions.pay`, `users.manage`, `audit.view`.

How to apply it:
- A DRF `HasPerm("orders.assign")` permission class, plus `get_queryset()` scoped by role. Example: a reseller only sees `Order.objects.filter(assigned_reseller=user)`.
- **Two serializers for products**: the public one never includes `price_primary` or margin; the staff one includes them when the user has `products.manage`.
- Return the permission list in `auth/me/` (`permissions: [...]`) so the UI can stop hard-coding the matrix.

---


---

## 6. Real-time (Channels + channels-redis, Uvicorn)

Your design, with these implementation details:

- **One consumer** at `/ws/?ticket=`, behind `TicketAuthMiddleware` + `AllowedHostsOriginValidator`.
- **Envelope:** `{type, data, ref}`.
- **Groups:** `user.{id}`, `conversation.{id}`, `staff`, `presence.resellers`.

**The consumer delegates to a handler registry.** It stays as thin as a view:

```python
class GatewayConsumer(AsyncJsonWebsocketConsumer):
    handlers = ws_registry

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        envelope = Envelope.parse(content)
        handler = self.handlers.resolve(envelope.type)
        await handler(self.session, envelope)
```

- Each client message type (`conversation.subscribe`, `message.send`, `typing.start`, `message.read`, `presence.ping`) is a small handler. It checks the permission and then calls the same facade the REST API uses. **Sending a message by REST or by WS runs the same code.**
- **Server events come only from `RealtimeObserver`.** It maps domain events to `(group, type, data)`. Facades never call `channel_layer` directly.
- **Presence:**
  - a Redis key `presence:{user_id}` with a 60 s TTL, refreshed by `presence.ping`;
  - the effective status combines that key with the manual `availability` field;
  - a change emits `presence.changed` to `staff`.
- **Assistant:** SSE on `/assistant/sessions/{id}/messages/`, served by an async DRF view on ASGI. Events are `delta`, `products`, `done` and `error`.

---

## 7. Where each part of the stack fits

| Tool | Use |
|---|---|
| **PostgreSQL full-text search** | Pre-computed weighted `search_vector` (name A, category B, features C, description D) with a GIN index and a `french_unaccent` text configuration. Used by `products/?search=` (`websearch_to_tsquery` + `ts_rank`) and `suggest/` (prefix tsqueries). The vector is refreshed inline on `ProductChanged`. No separate search service to run or keep in sync. |
| **pgvector** | `related/` and RAG for the assistant. Embed with Celery, never inside the request (the old search did). The assistant gets a tool `search_products(query, category, on_sale, max_price)` and returns `products[]`. |
| **Gemini** | `google-genai` async streaming. Keep the old history summary (Redis) and the ProductQuestion sentiment analysis (Celery follow-up task). |
| **Materialized views / aggregate tables** | `sales_daily(date, seller, category, method, revenue, cost, units, count)` and `sales_hourly(weekday, hour)`. `dashboard/` and `analytics/` read only from these. Refresh them with Celery beat every 5 min plus a targeted update in `on_commit` of a sale. Calculate "stock value over 22 weeks" with a weekly snapshot task, because history can't be rebuilt from the current stock. |
| **Redis** | Django cache (catalogue, `home/`, facets), Celery broker, the channel layer, presence, throttling. Use separate databases, e.g. db0 cache / db1 broker / db2 channels. |
| **Celery** | Emails (never synchronous SMTP, which the old project used), embeddings, exports, imports, aggregates, low-stock alerts, assistant analytics. Use separate queues: `default`, `ai`, `exports`. |
| **pgbouncer** | Supabase's pooler on port 6543 in *transaction* mode. Set `DISABLE_SERVER_SIDE_CURSORS=True` and `CONN_MAX_AGE=0`. Run migrations over the direct connection on 5432. |
| **Cloudinary** | Signed direct uploads (`sign_upload`) behind `MediaStorage`; `django-cloudinary-storage` only for Django admin. Resize and compress with Pillow (max 1600 px, WebP) before upload, or use Cloudinary's `eager` transformations. Set `NEXT_PUBLIC_MEDIA_HOST=res.cloudinary.com`. |
| **django-safedelete** | Product and Category: `SOFT_DELETE_CASCADE` off for products, and `all_objects` for the trash view. |
| **django-import-export** | Product CSV (`;` separator, oui/non booleans, category matched by name) and sales exports. |
| **WeasyPrint + openpyxl** | Sales PDF, dashboard PDF (build it with a **server-side** chart library such as matplotlib, never from image URLs sent by the client — the old dashboard PDF had SSRF/injection there), and xlsx. |
| **django-axes + throttling** | Login, `orders/track/`, `contact/`, `newsletter/`, `reseller-applications/`, `assistant/` (per user/IP plus a daily Gemini quota). |
| **django-csp / cors-headers** | `CORS_ALLOWED_ORIGINS=[https://celebobo.com]`, `CORS_ALLOW_CREDENTIALS=True`, and `CSRF_TRUSTED_ORIGINS` set to match. |
| **structlog** | A JSON logger with a `request_id` middleware. Pass `request_id` to Celery tasks through task headers. |
| **Schemathesis** | Run against `schema/` in CI. It only works well if every view has `@extend_schema` with the real serializers. |

---


---

## 8. Migrating data from the old project

Write a management command `import_legacy` that runs in this order:
1. **Users:**
   - `auth.User` + `Profile` → `User`;
   - `mukubwa` group → `role=mukubwa`, `revendeur` group → `revendeur`;
   - the old codes are 4 alphanumeric characters but the UI expects 4 digits, so regenerate them and keep a `legacy_code` field.
2. **Categories:** add `icon` and `order`. Drop `category_legacy` and copy its value into the FK.
3. **Products:** `image…image_three` → ProductImage. `badge`/`rating`/`reviews` → recompute them from the reviews (testimonies). `stock` = 0 until the first inventory count.
4. **Orders:** `attente` → `pending`, `traitement` → `assigned`, `terminé` → `delivered`; the address is unknown → empty snapshot.
5. **Ventes:** each old row = one unit (bulk sales created one row per unit) → `quantity=1`. You can group them by (order, product, price). `unit_cost` = the current `price_primary`; note that historical profit is approximate.
6. Conversations, Messages, Notifications, Testimonies, Favorites.
7. Embeddings: copy them (same model, 768 dimensions) or regenerate them.

Media are already on Cloudinary, so keep the same `public_id`s.

---


---

## 9. Old bugs that must not come back (write a test for each)

1. A user listing orders sees everyone's orders (`order_history` with no `user=` filter).
2. Any logged-in user can join any conversation by its id.
3. Cart endpoints are `csrf_exempt`, and the dashboard PDF endpoint has no auth.
4. `api/tasks/<id>/` is public and returns tracebacks.
5. A reseller can delete another reseller's sale.
7. `mtb2@gmail.com` is added to every email (`utils/email_custom.py:14`).
8. `Vente.date_achat` uses `auto_now_add`, so the date entered is ignored.
9. The cart ignores `price_solde`.
10. The referral is saved on `user` instead of `profile`, so it never saves.
11. Checkout runs without a transaction.
12. `Group.objects.get()` → 500 if the group is missing (replaced here by the `role` field).
13. Search returns a 500 when Gemini is down.

---


---

## 10. What the UI will need to adapt

| UI today | Backend v1 |
|---|---|
| Session cookie + `X-CSRFToken` read from `document.cookie` | JWT httpOnly cookies; the CSRF double-submit is handled by dj-rest-auth |
| `/admin/*`, `/profile/*`, `/orders/` (own), `/favorites/{id}/toggle/`, `/products/{id}/testimonies/` | `/bo/*`, `/me/*`, `/me/orders/`, `POST/DELETE /me/favorites/`, `/products/{slug}/reviews/` |
| Lookups by id | Storefront by slug, back office by id |
| `{count, next, previous, results, stats…}` | `{results, next, previous, meta}` |
| Multipart uploads to the API | Cloudinary signed upload + `uploads/complete/` |
| `window.open` on export URLs | 202 job → WS `job.completed` → download URL |
| `POST /assistant/message/` (JSON) | SSE sessions |
| WS `{action, channel}` / `{channel, payload}` | `{type, data, ref}` + ticket |
| Notification-based assignment (`/notifications/{id}/assign/`) | `/bo/orders/{id}/assign/` + reseller accept/decline |
| French status values (`attente`, `livree`…) | English API values; the UI keeps its French labels |
| Google login built from `API_URL.replace(/\/api\/?$/, "")` | Use `NEXT_PUBLIC_AUTH_URL` |

---

## 11. Build order

1. **Core:**
   - `core/` (registry, container, event bus, observability, `UseCaseViewSet`, errors, pagination factory, versioning);
   - settings split, Docker Compose (api, worker, beat, redis, pgbouncer), CI;
   - quality tooling: ruff, mypy, import-linter, pytest, pip-audit, bandit, pre-commit.
2. **Accounts:** auth (JWT cookies + Google), roles, permissions matrix, `/me/`.
3. **Catalogue:** read side, PostgreSQL full-text search, cache.
4. **Orders:** cart, pricing, checkout facade, state machine, messaging, notifications, WS gateway.
5. **Back office:** products, variants, stock, categories, uploads.
6. **Sales:** sales, conversion, refunds, commissions, payouts.
7. **Reporting:** aggregates, dashboard, analytics, exports.
8. **Assistant and audit:** assistant (RAG + SSE), audit API, legacy import.
9. **Hardening:** Schemathesis, throttling, CSP, load tests (Locust on checkout + WS fan-out).

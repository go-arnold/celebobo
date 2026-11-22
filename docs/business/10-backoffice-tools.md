# 10. Back-office tools

## Dashboard (`dashboard.view` — resellers and staff)

Figures are computed from **valid sales** (refunded amounts deducted) over a period: last 7 days,
30 days, 90 days, 12 months, year to date, or custom dates; optional filters by category, payment
method and (staff only) seller. **A reseller always sees only their own sales.**

| Widget | Content |
|---|---|
| Summary | Revenue, profit, number of sales, units, average basket — each with the previous period and the change in %; margin rate; today's revenue; open orders |
| Revenue series | Per day (short periods) or per month: revenue, profit, sales count, average basket |
| Payment split | Revenue and share per payment method |
| Top products | Best 5 by revenue, units or profit |
| Recent sales | Latest sales |
| Open orders | Orders not yet final (count + latest) |

Aggregates are refreshed every 10 minutes and shortly after any sale change; the dashboard updates live.

## Analytics (`analytics.view` — staff)

Same filters as the dashboard, plus:
- **Categories**: revenue, profit, units, margin rate and share per category;
- **Sellers ranking**: revenue, profit, sales, units, share per seller;
- **Peak hours**: sales per weekday × hour;
- **Slow movers**: up to 20 products in stock with no recent sale (stock and last sale date);
- **PDF report** of the period (`reports.analytics`, also available to resellers for their own figures).

## Exports and imports (jobs)

Long tasks run in the background as **jobs**: the request returns immediately (`202`), the job is
polled (`/jobs/{id}/`) and its file downloaded when done (`/jobs/{id}/download/`). A `job.completed`
event is pushed when it finishes. Users see only their own jobs; files are deleted after **7 days**.

| Job | Who | Formats | Limits |
|---|---|---|---|
| Sales export | `exports.sales` (resellers: own sales) | CSV, XLSX, PDF | 20,000 rows |
| Catalogue export | `exports.products` | CSV, XLSX | 20,000 rows |
| Analytics report | `reports.analytics` | PDF | — |
| Catalogue import | `imports.products` | CSV | 2,000 rows, 2 MB |
| Personal data ("Mes données") | `personal_data.export.own` (everyone, own data) | ZIP (JSON + HTML) | 1 per hour, link 48 h |

The personal data export has its own routes (`/me/data-export/`, see [§2](02-accounts.md#download-my-data)):
it is not listed or served by `/jobs/`, its download link expires after **48 hours** and its file is
deleted then, and each request and download is audited.

### Catalogue CSV import

- Columns: `slug`, `name`, `description`, `category`, `price`, `sale_price`, `cost_price`, `stock`,
  `stock_threshold`, `is_active`, `seo_title` (70 characters), `seo_description` (160). Required: **name, category, price**. Separator `;` or `,`, UTF-8.
- A row **with an existing slug updates** that product; **without slug it creates** one.
- `category` is the category **slug** (e.g. `smartphones`); booleans accept oui/non, true/false, 1/0, yes/no, vrai/faux.
- `stock`, when given, **sets** the stock (logged as a stock movement).
- **Dry run** first: validates every row and returns counts (to create / to update) and errors per
  row, without saving. The real import applies valid rows and skips invalid ones (each row is saved on its own).

### Invoices

PDF invoice of an order: clients for their own orders, back-office users for orders they can see.
Not available for cancelled orders. When fidelity points are on, it ends with the client's
**"Vos points de fidélité"** statement: points earned on this invoice (marked "en attente" until the
return period is over), points used on it, available balance, total and count of the client's
delivered orders (§12).

### Delivery receipts

A **signed delivery receipt** (PDF) is the proof that the order was handed over (plan step 3.4,
Code du numérique art. 58):

- It is issued **once**, when the order becomes **delivered**, and **e-mailed** to the client with
  the PDF attached. Its content is frozen then: order and receipt numbers (`R-{order number}`),
  client, delivery or pickup address, items, totals, payment method, date and time of handover,
  reseller, and how the delivery was confirmed (with the client's code, or by a manager without
  it, with the reason).
- That content is **signed** (HMAC-SHA256 with a key derived from the server secret). Every copy of
  the PDF is rendered from the frozen content, so it always matches the signature printed on it.
- Download: `/me/orders/{number}/receipt/` (client, `invoices.view.own`) and
  `/bo/orders/{id}/receipt/` (back-office, `invoices.view`). Before delivery: `receipt_unavailable`.
  An order delivered before receipts existed gets its receipt on the first download (not e-mailed).
- **Verification** (anyone): the public page `/verifier-recu` of the site, whose link (number and
  signature filled in) is printed on every receipt, both as text and as a **QR code** to scan with
  a phone, calls `POST /receipts/verify/` with the receipt
  number and the signature → `valid`, and if so the order number, delivery date and total, to
  compare with the paper. A receipt whose stored content was changed afterwards no longer verifies.
- Rotating the server secret (`DJANGO_SECRET_KEY`) makes existing signatures fail verification:
  rotate it only together with re-signing the receipts.

## Uploads (images)

Files go **directly from the browser to Cloudinary**, signed by the API:
1. `POST /uploads/sign/` with a purpose → signature;
2. upload to Cloudinary;
3. `POST /uploads/complete/` → the API verifies the upload and returns a media **id**, then used in
   forms (`image_ids`, `image_id`, `avatar_upload_id`).

A form with several images signs once, uploads them in parallel and records them together with
`POST /uploads/complete/batch/` (up to 8, all or none).

| Purpose | Who | Max size | Stored as |
|---|---|---|---|
| Product image | `products.manage` | 8 MB | ≤ 1600 px |
| Category image | `categories.manage` | 4 MB | ≤ 1200 px |
| Avatar | any logged-in user | 2 MB | 400×400, face-centred |
| Message attachment | any logged-in user | 5 MB | ≤ 1600 px |

Images only (JPEG, PNG, WebP…). Uploads that are **not used anywhere after 24 hours** are deleted
from Cloudinary by a daily sweep.

## Audit log (`audit.view` — admin)

Two journals, kept **365 days**:

1. **Data changes**: every create / update / delete on users (without passwords), categories,
   products, variants, reviews, orders, coupons, shipping zones, sales, payouts and reseller
   applications — with the before/after values, the author and the IP address. Filters: action,
   object type, object id, author, dates, search.
2. **Business events**: every domain event (order placed, sale recorded, role changed…) with its
   payload and author.

## Scheduled tasks

| Task | Frequency |
|---|---|
| Refresh sales aggregates (dashboard, analytics) | every 10 minutes (configurable) |
| Delete expired job files (7 days; personal data exports 48 h after they are ready) | hourly |
| Purge audit entries older than the retention period | daily |
| Delete orphan uploads | daily |
| Announce deals that start or end | every minute |
| Expire the points of clients with no order in the validity period (12 months) | daily |
| Retention rules of the privacy policy (one task per rule, below) | daily |

## Retention

The retention periods of the privacy policy (§6) are applied by daily tasks (`audit.apply_retention`,
one beat entry per rule so a failing rule never blocks the others). Each rule works by batches of
200 rows (one transaction per batch; the account rule adds a savepoint per account so that one
failure never blocks the others), is idempotent, logs its count and writes a
`RetentionApplied` event (rule, count) to the audit log on every real run, even with nothing to do.
The periods are domain constants: they come from the policy text, not from settings.

| Rule | What | Details |
|---|---|---|
| `accounts.inactive_clients` | Client accounts anonymised 3 years after the last activity; accounts deleted by the client lose the personal data left elsewhere 3 years after the deletion | [§2](02-accounts.md#inactive-accounts-retention) |
| `messaging.stale_conversations` | Conversations deleted 3 years after the client's last order and the last message | [§7](07-messaging-notifications.md#retention) |
| `resellers.rejected_applications` | Rejected reseller applications deleted 1 year after the decision | [§6](06-resellers.md#2-review-staff-reseller_applicationsreview) |
| `content.stale_subscribers` | Newsletter subscribers deleted after 3 years without (re)subscribing | [§8](08-content.md#newsletter) |
| `content.contact_messages` | Contact-form messages deleted 3 years after they were received | [§8](08-content.md#contact-form) |

To run them by hand: `python manage.py apply_retention [--rule NAME …] [--dry-run]`. With
`--dry-run` nothing changes and nothing is written to the audit log: the command prints, per rule,
how many rows would be affected and the first 50 (ids and dates only, no personal data).

Not covered by a rule yet: warranty and return files (1 year after the trial and warranty period)
do not exist yet (Phase 7); orders, invoices and payments are kept 10 years and none is that old;
the reseller's access to a client's contact details after delivery and the 12-month technical logs
(audit log, above) are handled elsewhere.

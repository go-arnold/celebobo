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

### Catalogue CSV import

- Columns: `slug`, `name`, `description`, `category`, `price`, `sale_price`, `cost_price`, `stock`,
  `stock_threshold`, `is_active`. Required: **name, category, price**. Separator `;` or `,`, UTF-8.
- A row **with an existing slug updates** that product; **without slug it creates** one.
- `category` is the category **slug** (e.g. `smartphones`); booleans accept oui/non, true/false, 1/0, yes/no, vrai/faux.
- `stock`, when given, **sets** the stock (logged as a stock movement).
- **Dry run** first: validates every row and returns counts (to create / to update) and errors per
  row, without saving. The real import applies valid rows and skips invalid ones (each row is saved on its own).

### Invoices

PDF invoice of an order: clients for their own orders, back-office users for orders they can see.
Not available for cancelled orders.

## Uploads (images)

Files go **directly from the browser to Cloudinary**, signed by the API:
1. `POST /uploads/sign/` with a purpose → signature;
2. upload to Cloudinary;
3. `POST /uploads/complete/` → the API verifies the upload and returns a media **id**, then used in
   forms (`image_ids`, `image_id`, `avatar_upload_id`).

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
| Delete expired job files | daily |
| Purge audit entries older than the retention period | daily |
| Delete orphan uploads | daily |

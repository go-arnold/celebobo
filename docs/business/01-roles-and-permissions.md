# 1. Roles and permissions

## Roles

| Role | Rank | Who |
|---|---|---|
| `anonymous` | 0 | Visitor who is not logged in |
| `client` | 1 | Customer account |
| `reseller` | 2 | Seller (revendeur) |
| `manager` | 3 | Shop manager (responsable) |
| `admin` | 4 | Administrator |
| `system` | 5 | Background jobs and automatic actions (never a person) |

**Roles are cumulative.** A role has every permission granted to its own rank and to every rank
below it: a manager can do everything a reseller and a client can, an admin everything a manager can.

Convenience groups used throughout the code:
- **back-office** = reseller, manager, admin (`actor.is_backoffice`);
- **staff** = manager, admin (`actor.is_staff`).

A deactivated account cannot log in, and its open sessions are revoked.

## Permission matrix

✓ = granted at that rank (and therefore to every rank above).

| Permission | What it allows | Anonymous | Client | Reseller | Manager | Admin |
|---|---|:-:|:-:|:-:|:-:|:-:|
| `assistant.chat` | Ask the AI assistant | ✓ | ✓ | ✓ | ✓ | ✓ |
| `account.view` / `account.update` | See and edit own profile | | ✓ | ✓ | ✓ | ✓ |
| `account.delete` | Delete (anonymise) own account — clients only, see §2 | | ✓ | ✓ | ✓ | ✓ |
| `addresses.manage` | Own address book | | ✓ | ✓ | ✓ | ✓ |
| `preferences.manage` | Own notification preferences | | ✓ | ✓ | ✓ | ✓ |
| `realtime.connect` | Open the WebSocket | | ✓ | ✓ | ✓ | ✓ |
| `assistant.history` | Keep and reopen assistant sessions | | ✓ | ✓ | ✓ | ✓ |
| `reviews.create` | Review a product (only if received, see §3) | | ✓ | ✓ | ✓ | ✓ |
| `favorites.manage` | Own favorites | | ✓ | ✓ | ✓ | ✓ |
| `invoices.view.own` | Download the invoice of own orders | | ✓ | ✓ | ✓ | ✓ |
| `media.upload` | Upload an avatar or a message attachment | | ✓ | ✓ | ✓ | ✓ |
| `conversations.use` | Read and write in own conversations | | ✓ | ✓ | ✓ | ✓ |
| `conversations.open_support` | Open a support thread | | ✓ | ✓ | ✓ | ✓ |
| `conversations.respond_proposal` | Accept / refuse a price proposal | | ✓ | ✓ | ✓ | ✓ |
| `notifications.view` | Own notifications | | ✓ | ✓ | ✓ | ✓ |
| `orders.place` | Place an order | | ✓ | ✓ | ✓ | ✓ |
| `orders.view.mine` | Own orders | | ✓ | ✓ | ✓ | ✓ |
| `orders.cancel.mine` | Cancel own pending order | | ✓ | ✓ | ✓ | ✓ |
| `push.devices` | Register browsers for push notifications | | ✓ | ✓ | ✓ | ✓ |
| `availability.update` | Set own availability (online / away / offline) | | | ✓ | ✓ | ✓ |
| `dashboard.view` | Back-office dashboard (scoped, see below) | | | ✓ | ✓ | ✓ |
| `products.view` | Back-office product list | | | ✓ | ✓ | ✓ |
| `invoices.view` | Invoice of any order they can see | | | ✓ | ✓ | ✓ |
| `jobs.view.own` | Own export/import jobs | | | ✓ | ✓ | ✓ |
| `exports.sales` | Export sales (CSV, XLSX, PDF) | | | ✓ | ✓ | ✓ |
| `reports.analytics` | PDF analytics report | | | ✓ | ✓ | ✓ |
| `conversations.moderate` | Close / reopen conversations they take part in | | | ✓ | ✓ | ✓ |
| `price.adjust` | Propose a price in an order thread | | | ✓ | ✓ | ✓ |
| `orders.view.assigned` | Orders assigned to them | | | ✓ | ✓ | ✓ |
| `orders.status.advance` | Move their order one step forward | | | ✓ | ✓ | ✓ |
| `orders.assignment.decline` | Give back an order assigned to them | | | ✓ | ✓ | ✓ |
| `referral.view.own` | Own referral kit and invitees | | | ✓ | ✓ | ✓ |
| `sales.view.own` | Own sales | | | ✓ | ✓ | ✓ |
| `sales.create` | Record a sale | | | ✓ | ✓ | ✓ |
| `sales.convert` | Convert an order into sales | | | ✓ | ✓ | ✓ |
| `sales.edit.own` | Edit own valid sales | | | ✓ | ✓ | ✓ |
| `commissions.view.own` | Own commissions and payouts | | | ✓ | ✓ | ✓ |
| `users.view` | User list | | | | ✓ | ✓ |
| `analytics.view` | Analytics pages | | | | ✓ | ✓ |
| `assistant.logs` | Assistant conversation logs | | | | ✓ | ✓ |
| `products.manage` | Create / edit / trash / restore products, variants, bulk actions, product images | | | | ✓ | ✓ |
| `stock.adjust` | Stock adjustments | | | | ✓ | ✓ |
| `categories.manage` | Categories (CRUD, order, images) | | | | ✓ | ✓ |
| `reviews.moderate` | Hide / publish reviews | | | | ✓ | ✓ |
| `contact.inbox` | Contact form messages | | | | ✓ | ✓ |
| `newsletter.view` | Newsletter subscribers (+ CSV export) | | | | ✓ | ✓ |
| `content.manage` | Pages, FAQ, banners | | | | ✓ | ✓ |
| `exports.products` / `imports.products` | Catalogue export / CSV import | | | | ✓ | ✓ |
| `conversations.assign` | Assign a support thread to a reseller | | | | ✓ | ✓ |
| `orders.view.all` | Every order | | | | ✓ | ✓ |
| `orders.assign` | Assign / reassign orders | | | | ✓ | ✓ |
| `orders.status.any` | Any forward transition, cancel, return | | | | ✓ | ✓ |
| `shipping.manage` | Shipping zones | | | | ✓ | ✓ |
| `coupons.manage` | Coupons | | | | ✓ | ✓ |
| `presence.view` | Who is online | | | | ✓ | ✓ |
| `resellers.view` / `resellers.manage` | Reseller list, rate, manager, activation | | | | ✓ | ✓ |
| `reseller_applications.review` | Approve / reject applications | | | | ✓ | ✓ |
| `sales.view.all` / `sales.edit.all` | Every sale | | | | ✓ | ✓ |
| `sales.refund` | Refund or return a sale | | | | ✓ | ✓ |
| `commissions.view.all` | Every reseller's commissions | | | | ✓ | ✓ |
| `users.manage` | Create users, change roles, activate / deactivate, send password reset | | | | | ✓ |
| `audit.view` | Audit log | | | | | ✓ |
| `embeddings.reindex` | Rebuild the assistant's product index | | | | | ✓ |
| `settings.manage` | Site settings (hotline, payment methods, rates…) | | | | | ✓ |
| `sales.delete` | Delete a sale | | | | | ✓ |
| `commissions.pay` | Record a commission payout | | | | | ✓ |

The current user's effective permissions are returned by `GET /api/v1/me/` (`permissions`).

## Data scoping ("same page, filtered data")

A permission opens a screen; **scoping decides which rows are visible**. Rows outside the scope
answer `404`, not `403`.

| Data | Client | Reseller | Manager / Admin |
|---|---|---|---|
| Orders | own orders | orders assigned to them | all |
| Conversations | own (as client) | assigned to them, or own as client | all |
| Sales | — | sales where they are the seller | all |
| Commissions, payouts | — | own | all |
| Dashboard and analytics figures | — | own sales only (seller filter forced to themselves) | all (optional seller filter) |
| Notifications, favorites, addresses, assistant sessions | own | own | own |

## Rules that hold regardless of permission

- Nobody can change **their own role** or **deactivate their own account**.
- Only **client** accounts can delete themselves; reseller and staff accounts are deactivated by an admin.
- A manager or admin account **cannot become a reseller**.
- A reseller can only act on orders **assigned to them** (advance, decline, propose a price).
- Only the **client of the order** can accept or refuse a price proposal.

# Celebobo — business logic

What the platform does, who can do what, and the rules behind each action.
Every rule here comes from the code: permissions (`apps/*/permissions.py`), domain rules and
errors (`apps/*/domain/`), services (`apps/*/services/`) and event handlers (`apps/*/handlers.py`).
When the code and this document disagree, the code wins — update the document.

| # | Document | Covers |
|---|---|---|
| 1 | [Roles and permissions](01-roles-and-permissions.md) | The five roles, the full permission matrix, data scoping |
| 2 | [Accounts](02-accounts.md) | Registration, login, profile, addresses, referral codes, staff accounts, deletion |
| 3 | [Catalogue](03-catalogue.md) | Categories, products, variants, prices, stock, reviews, favorites, search |
| 4 | [Cart, checkout and orders](04-cart-checkout-orders.md) | Cart, coupons, shipping, checkout, order workflow, assignment, cancellation, returns, invoices, tracking |
| 5 | [Sales and commissions](05-sales-commissions.md) | Recording sales, converting orders, refunds, commissions, payouts |
| 6 | [Resellers](06-resellers.md) | Applications, onboarding, referral kit, invitees, availability, management |
| 7 | [Messaging and notifications](07-messaging-notifications.md) | Conversations, price proposals, notifications, preferences, push, real time |
| 8 | [Site content](08-content.md) | Pages, FAQ, banners, site settings, contact form, newsletter |
| 9 | [AI assistant](09-assistant.md) | What it answers, limits, history |
| 10 | [Back-office tools](10-backoffice-tools.md) | Dashboard, analytics, exports/imports, uploads, audit log, scheduled tasks |
| 11 | [Error codes](11-error-codes.md) | Every business error the API can return |

## The business in one paragraph

Celebobo sells phones, computers and accessories in Kinshasa. A **client** browses the shop, fills a
cart and places an **order** (no online payment: Mobile Money or cash, settled with a person). Each
order opens a **conversation**. A **manager** assigns the order to a **reseller**, who talks with the
client, may adjust a price, and moves the order forward until delivery. Delivered orders are
**converted into sales**; each sale earns the reseller a **commission**, which an **admin** pays out.
Resellers also record walk-in sales directly, and recruit clients with their **referral code**.

## Glossary

| Term | Meaning |
|---|---|
| Client | A customer account (role `client`). |
| Reseller (revendeur) | A seller who handles assigned orders, records sales and earns commissions (role `reseller`). |
| Manager (responsable, "mukubwa") | Runs the shop: catalogue, all orders, assignment, analytics (role `manager`). |
| Admin | Everything a manager can do, plus users, payouts, deletions, audit and site settings (role `admin`). |
| Staff | Manager or admin. |
| Back-office | Reseller, manager or admin — anyone who can open `/admin`. |
| Order thread | The conversation created automatically for each order. |
| Support thread | A conversation a client opens without an order. |
| Conversion | Turning an order's lines into sales (one sale per line). |
| Referral code | A reseller's 4-digit code (1000–9999); clients who sign up with it are the reseller's invitees. |
| Job | An asynchronous export, import or report; its file is downloaded when ready. |

All amounts are in **US dollars** with 2 decimals. Dates are stored in UTC and shown in Kinshasa time.

# 4. Cart, checkout and orders

## Cart

Anyone can use a cart, logged in or not (`/cart/`).

- **Guest cart**: created on the first add; the API returns a cart **token** that the frontend sends
  back in the `X-Cart-Token` header.
- **Logged-in cart**: one cart per user.
- **Merge on login**: `POST /cart/merge/` with the guest token moves the guest lines into the user's
  cart (quantities added), keeps the guest coupon if the user cart has none, then deletes the guest cart.
- A line is a product (+ variant when the product has variants) and a quantity.
  Quantity is capped at **10 per line**; adding more silently caps it.
- Adding checks the product is sellable (active, in a visible category, variant chosen when needed)
  and that stock exists (`insufficient_stock`).
- The cart is **always repriced** from the catalogue: current price (sale price if any), shipping, coupon.
- A coupon can be applied to a non-empty cart (`empty_order` otherwise) and removed.

## Prices, shipping and coupons (the quote)

`POST /checkout/quote/` (anyone) and every cart view compute:

```
subtotal  = Σ unit price × quantity              (unit price = sale price if set, else price)
discount  = coupon discount, never above subtotal
shipping  = see below (0 if the coupon gives free shipping)
total     = subtotal − discount + shipping
```

**Shipping** depends on the delivery **city**:
1. The city is matched (case/accent-insensitive) against the cities of the active **shipping zones**;
   if none matches, the **default zone** is used; if there is no zone at all, global settings apply
   (free from **$199**, otherwise **$2.98**).
2. A zone has a fee, an optional free-shipping threshold and a delivery estimate (e.g. "24 à 48 h").
3. Shipping is **free** when the subtotal reaches the threshold, or when every line is a
   free-shipping product. Otherwise the fee is the **highest** of the zone fee / product-specific fees
   among the paying lines.
4. The quote returns how much is missing to reach free shipping.

Only one zone can be the default; marking a zone as default unsets the previous one.

**Coupons** (`coupons.manage`): code (stored upper-case, unique), kind `percent` (≤ 100) or `fixed`
amount, optional maximum discount, minimum subtotal, start/end dates, total usage limit, per-user
limit, free-shipping flag, active flag. A coupon is refused when:

| Reason | Rule |
|---|---|
| `unknown` | No such code |
| `inactive` | Deactivated |
| `not_started` / `expired` | Outside its dates |
| `minimum` | Subtotal below the minimum |
| `login_required` | It has a per-user limit and the visitor is not logged in |
| `exhausted` | Total usage limit reached |
| `already_used` | Per-user limit reached |

A percent discount is rounded to the cent and capped by the maximum discount. The coupon is
**redeemed** (counted) when the order is placed.

## Placing an order

`POST /orders/` — **logged-in users only** (`orders.place`). Requires an `Idempotency-Key` header:
retrying with the same key never creates a second order.

Input: lines, payment method (`orange_money`, `airtel_money`, `mpesa`, `cash`), an address
(an address-book id or a full address — `address_required`), optional coupon, optional note.

1. Lines are repriced from the catalogue with the stock **locked**; a missing product, variant or
   stock fails the whole order (`product_unavailable`, `variant_required`, `insufficient_stock`).
   Max **30 different lines** (`too_many_lines`), not empty (`empty_order`).
2. The order gets a public **number** `CB-XXXX-XXXX` (unambiguous letters and digits) and status **pending**.
3. The address, product names, images, SKUs and prices are **copied** into the order (snapshot).
4. The coupon is redeemed; the **stock is reserved** (reason `order`).
5. An **order thread** (conversation) is opened with the client.
6. Staff (managers and admins) are notified of the new order; it appears live in the back-office.

No money is taken online: payment happens with the reseller (Mobile Money or cash on delivery).

## Order statuses

```
pending ─► assigned ─► confirmed ─► paid ─► shipping ─► delivered ─► (returned)
   │            │            │         │          │
   └────────────┴────────────┴─────────┴──────────┴──► cancelled
```

| Status | Meaning |
|---|---|
| `pending` | Placed, waiting for a reseller |
| `assigned` | A reseller is in charge |
| `confirmed` | Availability and details confirmed with the client |
| `paid` | Payment received |
| `shipping` | Out for delivery |
| `delivered` | Received by the client — **final** |
| `cancelled` | Cancelled — **final** |
| `returned` | Returned after delivery — **final** |

### Who can move an order where

The order detail returns `allowed_transitions` for the current user — the frontend shows exactly those buttons.

| Actor | Allowed |
|---|---|
| Client (own order) | `pending → cancelled` only, with a reason: changed mind, ordered by mistake, too slow, cheaper elsewhere, other (+ optional details). |
| Reseller (order assigned to them) | **One step forward** only: assigned → confirmed → paid → shipping → delivered. Cannot cancel. |
| Manager / Admin | Any **forward** status (skipping steps allowed, except `assigned`, which only happens through assignment), **cancel** any non-final order, **return** a delivered order. |

Anything else is refused (`invalid_transition`). Every change is written to the order **history**
(status, time, actor name and role, note).

### Assignment

- Staff assign (`orders.assign`) an order to an **active reseller** (`reseller_not_found`). The
  assignable list shows each reseller's availability and number of open orders.
- Assigning a **pending** order moves it to **assigned**. Reassigning is allowed while the order is
  pending, assigned, confirmed or paid (`assignment_closed` after that); the history records it.
- On assignment the reseller **joins the order thread** and is notified.
- A reseller can **decline** an order that is still `assigned` to them (with a reason): it goes back
  to **pending**, they leave the thread, and staff are notified.

### What happens automatically on status changes

| Change | Effect |
|---|---|
| → `cancelled` | Reserved stock is **released** (reason `order`). The order thread is closed. |
| → `returned` | Stock comes back (reason `return`). Sales created from this order are marked **returned** and their commissions reversed (§5). The thread is closed. |
| → `delivered` | The order thread is closed. The client may now review the products. |
| Any change | Client notified (and the reseller, except for the assignment itself); real-time update for everyone watching. |

### Price adjustment

While an order is **assigned** or **confirmed**, the reseller in charge (or staff) can **propose a new
unit price** for a line in the order thread. The price must be > 0 and **not above the catalogue
price** at the time of ordering (`invalid_proposed_price`). If the client **accepts**, the line,
subtotal and total are recomputed (the coupon discount is capped to the new subtotal). See §7 for
the proposal flow.

## Customer views

- `/me/orders/` (own orders), `/me/orders/{number}/` detail, cancel while pending.
- **Invoice PDF** `/me/orders/{number}/invoice/` — not available for a cancelled order (`invoice_unavailable`).
  Back-office users get the invoice of any order they can see.
- **Public tracking** `POST /orders/track/` with the order number + the email **or** phone used for
  the order: returns the status timeline, without logging in.

## Back-office order list

`/bo/orders/` with filters (status, `unassigned`, reseller, payment method, dates, search on number,
client name or email) and **counts per status**. Resellers only see orders assigned to them.

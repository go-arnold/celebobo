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

**Shipping** depends on the delivery **city** (for a signed-in client who has not given one yet, the
city of their default address):
1. The city is matched (case/accent-insensitive) against the cities of the active **shipping zones**;
   if none matches, the **default zone** is used; if there is no zone at all, global settings apply
   (free from **$199**, otherwise **$2.98**).
2. A zone has a fee, an optional free-shipping threshold and a delivery estimate (e.g. "24 à 48 h").
3. Shipping is **free** when the subtotal reaches the threshold, or when every line is a
   free-shipping product. Otherwise the fee is the **highest** of the zone fee / product-specific fees
   among the paying lines.
4. The quote returns how much is missing to reach free shipping.

Only one zone can be the default; marking a zone as default unsets the previous one.

**Zone pricing.** Each zone has a pricing mode (`pricing`), set in the back-office (Settings → Shipping zones, `shipping.manage`):

| Mode | At checkout | Then |
|---|---|---|
| `flat` (default) | The zone fee, free from its threshold, as above | — |
| `quote` — *sur devis* | Shipping **0**, the quote says `shipping_quote_required`; no free-shipping threshold | A reseller quotes the fee in the order thread; the client accepts it or cancels free of charge (see *Zones quoted on request* below) |
| `pickup` — *retrait sur place* | Shipping **0**; the quote returns the shop's `pickup_address` | The client collects the order at the shop |

The delivery policy's "Autres localités" row is the **default zone** set to `quote`. There is at
most **one pickup zone**, it needs an address and can't be the default (errors on `pricing`,
`pickup_address`, `is_default`). It is **chosen**, never matched from a city: the quote and the
order take `pickup: true`; without an active pickup zone the answer is `pickup_unavailable`. Every
quote says whether pickup is offered (`pickup_available`).

**Fidelity points**: with `points`, the client chooses how many of their points pay part of the
products, 1 point = $1, up to their balance and the products after the coupon (see
[loyalty](12-loyalty.md)); `total = subtotal − discount − points + shipping`. The quote lowers the
amount asked to what is available (`points_available`); `POST /orders/` refuses it with
`points_unavailable` instead.

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

**Guessing codes is limited** to 20 attempts per hour per account (or per IP for visitors): every
"apply coupon" on the cart counts, and so does every quote whose code is **refused**. A quote with
a valid code is never counted, so checkout can re-quote freely. Past the limit, the cart and quotes
carrying a code answer `429`; quotes without a code still work.

## Placing an order

`POST /orders/` — **logged-in users only** (`orders.place`). Requires an `Idempotency-Key` header:
retrying with the same key never creates a second order.

Input: lines, payment method (`orange_money`, `airtel_money`, `mpesa`, `cash`), an address
(an address-book id or a full address — `address_required`), optional coupon, optional note,
optional `pickup` (collect at the shop; the address then only gives the contact name and phone).

0. A client can have at most **3 pending orders** at once (`ORDERS_MAX_PENDING_ORDERS`), because
   each one reserves stock (`too_many_pending_orders`). Assigned or cancelled orders free a place.
1. Lines are repriced from the catalogue with the stock **locked**; a missing product, variant or
   stock fails the whole order (`product_unavailable`, `variant_required`, `insufficient_stock`).
   Max **30 different lines** (`too_many_lines`), not empty (`empty_order`).
2. The order gets a public **number** `CB-XXXX-XXXX` (unambiguous letters and digits) and status **pending**.
3. The address, product names, images, SKUs and prices are **copied** into the order (snapshot),
   with the delivery method (`delivery` or `pickup`), the pickup address, the zone's delivery
   estimate and, for a zone quoted on request, `awaiting_shipping_quote: true`.
   Each line also records its share of the order's **coupon** (`discount`) and **points**, and the
   **real money** paid for it (`amount_paid` = line total − both); see *Line amounts* below.
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
| Client (own order) | **Cancel** until the order is out for delivery (`pending`, `assigned`, `confirmed` or `paid` → `cancelled`), free of charge, with a reason: changed mind, ordered by mistake, too slow, cheaper elsewhere, other (+ optional details). `expired` is reserved for the system. A paid order is refunded (see *Refunds*). |
| Reseller (order assigned to them) | **One step forward** only: assigned → confirmed → paid → shipping → delivered. Cannot cancel. Marking it delivered needs the client's **delivery code** (below). |
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
- A **pending** order that nobody assigns within **48 hours** (`ORDERS_PENDING_TTL_HOURS`) is
  cancelled by the system with the reason `expired`; its stock is released and the client is
  notified like for any cancellation. The delay counts from the last time the order became pending,
  so a declined order gets a fresh 48 hours. The check runs every hour.

### What happens automatically on status changes

| Change | Effect |
|---|---|
| → `cancelled` | Reserved stock is **released** (reason `order`). Points spent on it come back and the points it would earn are dropped. The order thread closes 7 days later (§7). Cancelled after payment (`paid` or `shipping`): a refund is owed (below). |
| → `returned` | Stock comes back (reason `return`). Sales created from this order are marked **returned** and their commissions reversed (§5). The thread closes 7 days later (§7). |
| → `delivered` | The order thread closes 7 days later (§7). The client may now review the products and rate the reseller. |
| Any change | Client notified (and the reseller, except for the assignment itself); real-time update for everyone watching. |

### Failed deliveries

The delivery policy: the reseller tries **twice, on two working days**; then the order is cancelled,
and a paid order is refunded within 5 working days, **delivery fee deducted**.

1. While the order is **out for delivery** (`attempt_not_allowed` otherwise), the reseller in charge
   (or staff) records each failed attempt (`POST /bo/orders/{id}/delivery-attempts/`): a reason —
   client absent, unreachable, wrong address, parcel refused, other — and an optional note. The
   attempts appear on the order (`delivery_attempts`, for the client too) and the client is
   notified that the reseller will come back another working day.
2. Working days are **Monday to Saturday**: several attempts on the same day count as one day, and
   a Sunday does not count.
3. When failed attempts fall on **2 different working days**, the system cancels the order with the
   reason `delivery_failed` (never chosen by a client). As for any cancellation the stock is
   released and spent points come back; a paid order owes `refund_due` = total **minus the
   delivery fee**, and the staff alert says **5 working days**.

### Rating the reseller

Once the order is **delivered** (or returned after delivery), its client can rate the reseller who
handled it: a score from **1 to 5** and an optional comment (`POST /me/orders/{number}/rating/`).
One rating per order (`already_rated`); not before delivery, nor for an order no reseller handled
(`order_not_ratable`). The client's order detail says `can_rate` and shows the `rating` given. The
reseller is notified, and the average and count appear in the resellers directory (§6).

### Delivery code

Delivery is confirmed by the client, through a code (owner's decision of 16 Nov 2026):

1. When the order becomes **confirmed** (or later, if staff skip that step), it gets a random
   **6-digit code**. The client receives it by **e-mail** (always, whatever their notification
   preferences) and in their notifications, and sees it on the order page until the order is
   delivered (`delivery_code`, client view only). Nobody in the back-office ever sees it.
2. At handover, once the client has the order in hand and in good condition, they give the code to
   the reseller, who enters it to mark the order **delivered** (`delivery_code` on the transition).
   Without it: `delivery_code_required`; a wrong code: `invalid_delivery_code`, with the attempts
   left (`meta.attempts_left`). Each wrong code is counted even though the delivery is refused.
3. After **5 wrong codes** the code is **locked** (`delivery_code_locked`): staff are alerted and
   the order detail says `delivery_code_locked`.
4. A **manager** (or admin) can confirm a delivery **without the code**, giving a **reason**
   (`delivery_reason_required` otherwise); this is recorded in the audit log
   (`DeliveredWithoutCode`, with the reason). Staff may also enter the code like a reseller.
5. The code itself never appears in events, the audit log or the back-office output.

### Refunds

An order cancelled once paid (`paid` or `shipping`, by the client or by staff) owes the client what
they really paid: `refund_due` = the order total (coupon and points were not money; the points
come back to their balance). The delivery policy gives **72 hours** to refund (art. 63). After
failed deliveries (above) the delivery fee is deducted and the delay is **5 working days**.

1. Staff and the reseller in charge are notified ("Remboursement à effectuer").
2. The back-office order list has a **refund pending** filter (`status=refund_pending`, with its
   count); each order says `refund_status`: `due`, then `done`.
3. Once the money is given back, staff record it (`orders.refund`,
   `POST /bo/orders/{id}/refund/`, optional note such as the Mobile Money reference). The order
   keeps `refunded_at` and the note, the history records it and the client is notified. Recording
   it twice, or for an order with nothing owed, is refused (`no_refund_due`).

### Zones quoted on request

An order placed in a `quote` zone is recorded normally, with **no shipping fee** and
`awaiting_shipping_quote: true` (delivery policy, "Votre zone n'est pas reconnue ?"):

1. The reseller in charge (or staff) sends the fee and the delivery estimate in the order thread
   (`shipping.quote`, see §7). The amount stays in the thread as a trace.
2. Until the client accepts a fee, **nothing moves forward**: the reseller can't confirm the order,
   staff can only cancel it; the client can cancel it free of charge, as any order before delivery.
3. When the client **accepts**, the fee and estimate are written to the order, the total is
   recomputed and the fee is **fixed**: no further quote is possible (`shipping_not_quotable`).
   The history records it and the order can be confirmed. A refusal changes nothing; the reseller
   can send another quote.

### Price adjustment

While an order is **assigned** or **confirmed**, the reseller in charge (or staff) can **propose a new
unit price** for a line in the order thread. The price must be > 0 and **not above the catalogue
price** at the time of ordering (`invalid_proposed_price`). If the client **accepts**, the line,
subtotal and total are recomputed (the coupon discount is capped to the new subtotal). See §7 for
the proposal flow.

### Line amounts

Commissions, referral points and partial returns work per line, so every line knows what it really
cost the client:

| Field | Meaning |
|---|---|
| `discount` | The line's share of the order's coupon discount |
| `points` | The line's share of the fidelity points used on the order |
| `amount_paid` | Real money paid for the line: `unit_price × quantity − discount − points` |

- The coupon is shared in proportion to the line totals; the points in proportion to what each
  line still costs after the coupon (points pay the products after the discount).
- Shares are rounded to the cent and always add up exactly to the order's amounts; any leftover
  cent goes to the line with the largest rounding remainder.
- Shipping belongs to the order, never to a line.
- A price adjustment shares the coupon and points out again over all lines.
- Orders placed before this existed were filled in once by the migration, with the same rule.
- Coupon and fidelity points are the **non-real money** of an order (store credit and Cagnotte
  campaigns will join them later); sale and deal
  prices are real money. The order details show the three fields on each line.

### Returning part of an order

Staff (`orders.status.any`) can take back **some units of one line** of a **delivered** order:
`POST /bo/orders/{id}/items/{item_id}/return/` with `quantity` and an optional `reason`, and an
`Idempotency-Key` header. Refused when the order is not delivered (`line_not_returnable`) or the
quantity is more than what is left on the line (`invalid_return_quantity`, with `remaining`).

- The return keeps its share of the line amounts: real money owed back (`amount_paid`), coupon and
  points. A partial return takes its proportion rounded down; the last units take what is left,
  so the returns of a line add up exactly to it.
- The units go back to stock (reason `return`).
- The sale made from that line is refunded for those units and the reseller's commission shrinks in
  proportion (§5); the client's points follow (§12). All of this is one transaction: if any part
  fails, nothing is recorded.
- When every unit of every line has come back, the order becomes **returned** by itself.
- Returning the whole order afterwards (status `returned`) restocks only the units still out, and
  marks every unit as returned.
- Order details show `returned_quantity` and `returned_amount` (real money owed back) on each line.

## Customer views

- `/me/orders/` (own orders), `/me/orders/{number}/` detail, cancel until out for delivery.
- **Invoice PDF** `/me/orders/{number}/invoice/` — not available for a cancelled order (`invoice_unavailable`).
  Back-office users get the invoice of any order they can see. It prints the points used in the
  totals and the client's **"Vos points de fidélité"** statement (§12).
- **Delivery receipt PDF** `/me/orders/{number}/receipt/` — signed, issued and e-mailed at delivery
  (see [back-office tools](10-backoffice-tools.md#delivery-receipts)); before delivery
  `receipt_unavailable`.
- **Public tracking** `POST /orders/track/` with the order number + the email **or** phone used for
  the order: returns the status timeline, without logging in.

## Back-office order list

`/bo/orders/` with filters (status, `unassigned`, reseller, payment method, dates, search on number,
client name or email — e-mail for staff only) and **counts per status**. Resellers only see orders
assigned to them, without the client's e-mail ([roles](01-roles-and-permissions.md#data-scoping-same-page-filtered-data)).

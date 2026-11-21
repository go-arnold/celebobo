# 5. Sales and commissions

A **sale** is one product line actually sold: what the business counts as revenue, profit and
commission. Sales come from two sources: **recorded directly** (walk-in, phone, WhatsApp…) or
**converted from an order**.

## Recording a sale

`POST /bo/sales/` (one sale) or `/bo/sales/bulk/` (several lines at once) — `sales.create`.
Both require an `Idempotency-Key` header.

| Field | Rules |
|---|---|
| Product (+ variant) | Must be sellable and in stock (`insufficient_stock`). |
| Quantity | ≥ 1. |
| Unit price | The **final** price actually paid (may differ from the catalogue price). |
| Payment method | Orange Money, Airtel Money, M-Pesa, cash. |
| Sold at | Defaults to now; **cannot be in the future** (`invalid_sale_date`). |
| Sold to | Free text (buyer's name), optional; or a buyer account. |
| Seller | A **reseller always records sales as themselves**. Staff may attribute the sale to any reseller or staff member (`invalid_seller`); without a seller the sale is theirs. |

On recording:
- the **cost price**, the product's **origin** (Celebobo / partner) and, for a partner product,
  **Celebobo's gain per unit** at that moment are copied into the sale (for profit and commission:
  editing the product later changes nothing for past sales);
- stock is **taken** (reason `sale`) and the product's sales counter increases;
- if the seller is a **reseller**, a commission is earned (below);
- dashboards and analytics update in real time.

**Profit** = (unit price − unit cost) × quantity (unknown when the product has no cost price).

## Converting an order into sales

`POST /bo/orders/{id}/convert-to-sales/` — `sales.convert`, `Idempotency-Key` required.
`/bo/orders/convertible/` lists recent orders and whether each can be converted.

- **One sale per order line**, same quantity; the final unit price can be overridden per line.
- The **seller** is the reseller assigned to the order, or else the person converting.
- Payment method defaults to the order's; "sold to" defaults to the client's name; the buyer is the client.
- Stock is **not** taken again (it was reserved when the order was placed).
- An order **cannot be converted** if it is cancelled or returned, if it is not **delivered** yet
  (`not_delivered`: delivery is confirmed first, with the client's code, see §4), if any of its lines
  was already converted (`already_converted`), or if no line still points to a product
  (`no_products`). `/bo/orders/convertible/` lists delivered orders only.

## Editing a sale

`sales.edit.own` (reseller, own sales) / `sales.edit.all` (staff). Only **valid** sales can be edited
(`sale_not_editable`). Editable: unit price, payment method, sold at, sold to. The product and quantity
cannot change (delete and re-record instead). A price change recomputes the commission.

## Refund and return

`POST /bo/sales/{id}/refund/` — `sales.refund` (staff), `Idempotency-Key` required.

| Kind | Effect |
|---|---|
| **Refund** (`refund`) | Money given back, the product stays with the client. Amount = any part of what remains refundable (default: all of it). Sale status → `refunded`. |
| **Return** (`return`) | The product comes back: the whole remaining amount is refunded, stock is restocked (reason `return`), sales counter decreases. Sale status → `returned`. |

- Several partial refunds are possible until the total is reached (`refund_exceeds_total`).
- A returned sale cannot be refunded again (`already_returned`).
- A sale that came **from an order** cannot be returned here: return the **order** instead
  (`return_through_order`), which returns all its sales at once, or return **some units of the
  line** on the order (§4): the sale is refunded `unit price × units` (the last units refund
  whatever is left and mark it `returned`; before that it shows `refunded`), its sales counter and
  `returned_quantity` follow, and the commission is reversed in proportion.
- The commission is reversed **in proportion** to the refunded amount.

## Deleting a sale

`DELETE /bo/sales/{id}/` — **admin only** (`sales.delete`). The commission is voided; for a sale recorded
directly (not from an order) the stock comes back (reason `correction`); the sales counter decreases.

## Lists, totals and exports

- `/bo/sales/`: filters by period (2, 7, 30, 90 days or dates), payment method, status, seller,
  product, search. Each page returns **totals** for the filter: revenue, profit, count, units, average basket.
- Resellers see their own sales only.
- **Export** (`exports.sales`): CSV, Excel or PDF of the current filter, produced as a job (§10).

## Commissions

Every reseller earns by the **same rules**; there is no per-reseller rate any more (it was removed
with the rules below).

### Rules decided on 16 Nov 2026

These rules were set by the owner and **replace** the earlier per-reseller rate (7 % by default) and
the figures of the v0.9 policy documents. The shares are constants of the code
(`apps/sales/domain/rules.py`), not settings.

Each **sale line** earns, on the **amount paid** for it (unit price × quantity, in real money):

| Product | Commission |
|---|---|
| **Celebobo** product | the **smaller** of **10 %** of the amount paid and **50 %** of the line's **gross margin** (amount paid − unit cost × quantity). A margin of 0 or less earns **nothing**. |
| Celebobo product **without a purchase price** | **10 %** of the amount paid (the margin cannot be known, so only the 10 % applies). |
| **Partner** product | the **smaller** of **10 %** of the amount paid and **20 %** of **Celebobo's gain** (gain per unit × quantity). |

- Each amount is **rounded to the cent** (half up) before the smaller one is taken.
- The cost, origin and gain are the ones **copied into the sale** when it was recorded or converted.
- **Nothing at all** on an order that used **any non-real money**: points (`points` > 0) or a
  coupon / promotion (`discount` > 0). This applies to the **whole order**, every line, not just
  the share paid that way. Sale prices and daily deals are real money and earn normally.
- **Nothing** on a reseller's **own purchases** (the buyer is the reseller selling).
- Sales **recorded directly** with a reseller as seller follow the same line rules (there are no
  points or coupons on them). Staff can record such a sale for a reseller.
- Sales by managers or admins (as seller) earn no commission.

Whether a sale earns at all (reseller seller, not their own purchase, real money only) is decided
**once**, when it is recorded or converted, and kept on the sale (`commissionable`).

### Ledger

- **Earned**: when a commissionable sale is recorded or converted, if the rules give more than 0.
- **Reversed**: on refund/return, in proportion to the refunded amount: earned × refunded ÷ sale
  total (never more than what is left).
- **Voided**: when a sale is deleted, or before being recomputed after a **price edit**: the new
  price is run through the same rules (with the sale's copied cost, origin and gain), so an edit can
  lower, raise, cancel or start the commission.

Every movement is a ledger entry: earned / reversed, **rule**, base amount, amount, note and
date of validation. Amounts are never changed afterwards: a refund adds a reversal entry. The
`rule` says which cap set the amount: `paid` (10 % of the amount paid), `margin` (50 % of the
margin), `partner_gain` (20 % of Celebobo's gain), `unknown_cost` (10 %, no purchase price); a
reversal repeats the rule of what it reverses. Entries written before 16 Nov 2026 have
`legacy_rate` (earned with the reseller's own rate, which is no longer stored: on an earned entry
the rate is amount ÷ base).

### Commission lifecycle: pending → validated → cancelled

Reseller policy §4, with the 7-day trial period of the warranty policy (`VALIDATION_DAYS`):

| Status | When |
|---|---|
| **Pending** (`pending`, « En attente ») | From the moment it is earned until **7 days after the order was delivered** (for a manual sale: 7 days after its sale date). A sale converted from an order counts from the delivery recorded on the order, whatever its sale date. |
| **Validated** (`validated`, « Validé ») | After those 7 days. Only validated commission is **payable**. |
| **Paid** (`paid`) | Validated and settled by a paid statement (below). |
| **Cancelled** (`cancelled`, « Annulé ») | The sale was fully refunded or returned, or deleted. |

- Each entry carries `available_at`, the moment it becomes validated. A reversal (refund, return,
  edit, deletion) takes the date of the earning it offsets, so it lowers what is pending when the
  commission is still pending, and what is validated otherwise — it never moves money from one to
  the other.
- A full refund **before** validation leaves nothing pending and nothing ever becomes payable. A
  full refund **after** validation cancels the validated amount; if it was already paid, the
  balance goes negative and is **deducted from the next payout** (policy §4). A partial refund
  stays proportional.
- Entries written before this rule existed were already counted as due: they are validated.

### Balances

- **Pending** = Σ entries not validated yet.
- **Validated** = Σ entries validated (net of reversals).
- **Delivery fees** = Σ delivery fees credited back (below).
- **Paid** = Σ payouts.
- **Due (payable)** = validated + delivery fees − paid.

| View | Who | Content |
|---|---|---|
| `/bo/commissions/overview/` | staff | Per reseller: earned this month, earned total, pending, validated, delivery fees, paid total, due, next payout date |
| `/bo/commissions/summary/` | reseller (own) / staff (`?reseller_id=`) | Same figures for one reseller, with the payout threshold ($5) |
| `/bo/commissions/series/` | same | Earned and paid per month |
| `/bo/commissions/` | same | Ledger entries, each with its `status` and `available_at` |

The resellers directory shows the same **due** (`commission_due`: validated + delivery fees − paid).

### Delivery fees credited back

Owner's decision of 18 Nov 2026 (reseller policy §3.4): the reseller who delivers an order remits
**everything** collected (§6); the **delivery fee** the client paid comes back to them on their
next payout, on its own line « Frais de livraison ».

- Credited when the order becomes **delivered**, to the reseller **assigned** to it (the one who
  entered the client's delivery code, or for whom staff confirmed the handover). It is payable at
  once: no trial period, it is not a commission.
- Nothing for a **pickup**, a **free delivery** (fee 0), or an order with no reseller.
- Kept when the order is later **returned** (whole or line by line): returns refund the products,
  never the delivery fee, and the delivery did take place. Taken back (a negative line) if the
  order is ever **cancelled** after the credit — today a delivered order cannot be cancelled, so
  this is a safeguard only.

## Payouts

Reseller policy §5: payouts on the **1st and the 16th** of each month, from **$5**.

### Statements

A periodic task (`sales.prepare_payouts`, Celery beat, every hour) prepares, **on the 1st and the
16th only**, a **payout statement** (« relevé ») for every reseller whose payable lines reach
**$5** (`PAYOUT_THRESHOLD`):

- A statement takes every ledger entry **validated before the payout date** (00:00 in the shop's time
  zone, `TIME_ZONE`) and every delivery fee credited before it, that no statement settled yet:
  commissions, reversals (deductions) and delivery fees. Its total is their sum.
- **Below $5** (or negative after a deduction) nothing is prepared: everything rolls over to the
  next payout date.
- One statement per reseller and date: the hourly runs of the same day prepare it once.
- A statement still **unpaid** on the next payout date is **replaced** (`cancelled`) by the new
  statement, which takes its lines back.
- When any sale or order of the reseller is refunded, returned, edited or deleted, **even one
  already paid**, every unsettled line validated before the payout date joins the prepared
  statement and its totals follow, so the statement always equals what is due; a statement left
  with nothing to pay is cancelled.
- Overlapping runs of the task skip a statement another run has just prepared.
- **Take-over** (migration `sales/0005`): resellers already paid with the former free-amount payouts
  get one `paid` statement that settles their whole history at what they were paid; what was still
  due (earned − paid) is carried over as a single line « Reprise : solde dû au passage aux relevés »
  of their next statement.
- The reseller is notified (« Relevé de paiement du … ») and their commissions page refreshes in
  real time.

| Endpoint | Who | Content |
|---|---|---|
| `GET /bo/payout-statements/` | reseller (own) / staff (`?reseller_id=`, `?status=prepared\|paid\|cancelled`) | Statements: payout date, status, commissions, delivery fees, total, prepared and paid dates |
| `GET /bo/payout-statements/{id}/` | same (a reseller gets `statement_not_found` for another's) | The statement with its lines: `commission` (per sale, with the order number), `reversal`, `delivery_fee`, `delivery_fee_reversal` |

No PDF yet: the statement is shown in the back-office only.

### Paying a statement

`POST /bo/payouts/` with `statement_id` — **admin only** (`commissions.pay`), `Idempotency-Key`
required; optional `note` (e.g. "M-Pesa") and `paid_at` (not in the future).

- The payout is the statement's **total**; the statement becomes `paid` and its commissions show
  as paid.
- Only a **prepared** statement (`statement_not_payable` once paid or replaced;
  `statement_not_found`).
- Never more than what is **due right now** (`payout_exceeds_due`, with the due amount): e.g. a
  commission cancelled after an earlier payment lowers the balance.
- Records who paid. The reseller is notified (« Paiement reçu ») and sees their payouts and the
  updated balance in real time. Payouts list their statement and payout date.

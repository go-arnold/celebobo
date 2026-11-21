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

Every movement is a ledger entry: earned / reversed, **rule**, base amount, amount, note. The
`rule` says which cap set the amount: `paid` (10 % of the amount paid), `margin` (50 % of the
margin), `partner_gain` (20 % of Celebobo's gain), `unknown_cost` (10 %, no purchase price); a
reversal repeats the rule of what it reverses. Entries written before 16 Nov 2026 have
`legacy_rate` (earned with the reseller's own rate, which is no longer stored: on an earned entry
the rate is amount ÷ base).

**Balance due** = Σ ledger entries − Σ payouts.

| View | Who | Content |
|---|---|---|
| `/bo/commissions/overview/` | staff | Per reseller: earned this month, earned total, paid total, due |
| `/bo/commissions/summary/` | reseller (own) / staff (`?reseller_id=`) | Same figures for one reseller |
| `/bo/commissions/series/` | same | Earned and paid per month |
| `/bo/commissions/` | same | Ledger entries |

## Payouts

`POST /bo/payouts/` — **admin only** (`commissions.pay`), `Idempotency-Key` required.

- Only to a **reseller** (`not_a_reseller`), for an amount **not above the balance due**
  (`payout_exceeds_due`), at a date not in the future; with an optional note (e.g. "Orange Money").
- Records who paid. The reseller sees their payouts and the updated balance in real time.

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
- the **cost price** of the product at that moment is copied into the sale (for profit);
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
- An order **cannot be converted** if it is cancelled or returned, if any of its lines was already
  converted (`already_converted`), or if no line still points to a product (`no_products`).
- If the order was not yet delivered, converting marks it **delivered** ("Commande convertie en ventes").

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
  (`return_through_order`), which returns all its sales at once.
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

Each reseller has a **commission rate** (default **7 %**, between 0 and 50 %), set by staff.

- **Earned**: when a sale is recorded or converted with a **reseller** as seller:
  `commission = sale total × reseller's rate at that moment`, rounded to the cent.
  Sales by managers or admins earn no commission.
- **Reversed**: on refund/return, proportionally to the refunded amount (never more than what was earned).
- **Voided**: when a sale is deleted, or before being recomputed after a price edit (the original rate is kept).
- Changing a reseller's rate affects **future** sales only.

Every movement is a ledger entry (earned / reversed, rate, base amount, amount, note).

**Balance due** = Σ ledger entries − Σ payouts.

| View | Who | Content |
|---|---|---|
| `/bo/commissions/overview/` | staff | Per reseller: rate, earned this month, earned total, paid total, due |
| `/bo/commissions/summary/` | reseller (own) / staff (`?reseller_id=`) | Same figures for one reseller |
| `/bo/commissions/series/` | same | Earned and paid per month |
| `/bo/commissions/` | same | Ledger entries |

## Payouts

`POST /bo/payouts/` — **admin only** (`commissions.pay`), `Idempotency-Key` required.

- Only to a **reseller** (`not_a_reseller`), for an amount **not above the balance due**
  (`payout_exceeds_due`), at a date not in the future; with an optional note (e.g. "Orange Money").
- Records who paid. The reseller sees their payouts and the updated balance in real time.

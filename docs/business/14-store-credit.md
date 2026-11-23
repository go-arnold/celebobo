# 14. Store credit (avoir)

Decided by the owner on 18 Nov 2026: a **balance in dollars**, separate from the fidelity points,
that pays **products and delivery**, valid **6 months**. It is **non-real money**: an order that
uses any of it earns no commission (§5) and no referral points (§12). App `apps/credit`.

## Where it comes from

- A **change of mind during the 7-day trial** (warranty claim, §13): staff choose the outcome « Avoir
  de 6 mois ». The unit comes back through the order's line return (stock, points taken back) and
  what the client paid for it in money becomes store credit instead of a refund.
- Each credit is valid **6 months** from the day it is given (`VALIDITY_MONTHS`).

## Spending it

- At checkout (`POST /checkout/quote/`, `POST /orders/`) the client chooses an amount
  (`store_credit`). The quote answers `store_credit_available` (the balance, capped at what is left
  to pay after the coupon and the points, **delivery included**) and `store_credit` (applied).
  Asking more than the total is simply capped; asking more than the balance at checkout is refused
  (`store_credit_unavailable`, 409).
- Order: `store_credit` is deducted from the total (`total = subtotal − discount − points −
  store_credit + shipping_fee`). It pays the **products first** (spread over the lines as `credit`,
  like the points), the rest pays the delivery. A line's `amount_paid` is the real money only.
- The credit closest to its expiry is used first. Each spending remembers the credit it came from.

## Given back

| What happens | Credit |
|---|---|
| The order is cancelled or returned | everything it used comes back |
| A line is returned | its share of the credit comes back |
| The price goes down (adjustment) and the credit is no longer all needed | the excess comes back |

Credit given back returns **to the credit it came from, with the same expiry**. Movements:
`issued`, `spent`, `restored`, `expired`.

## Expiry

A daily task (`credit.expire`) removes what is left of a credit 6 months old (an `expired`
movement).

## « Mon avoir »

`GET /me/store-credit/` (`store_credit.view.own`, every role that shops): the balance, the next
expiry and the last 50 movements (kind, amount, date, order number, expiry of a credit, note). The
invoice shows « Avoir utilisé » under the totals; order pages too (back-office: « pas de
commission »).

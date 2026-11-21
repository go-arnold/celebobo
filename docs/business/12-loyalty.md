# 12. Loyalty programmes

Three programmes, each **off until an admin turns it on**. Every rule below is a setting an admin
edits in `/bo/loyalty/settings/` (`loyalty.manage`); `GET /settings/public/` returns them under
`programmes`, and the shop only shows a programme that is enabled.

## Celebobo Plus (membership)

| Rule | Default |
|---|---|
| Benefit | Free delivery with no minimum in the zones marked for members (Bukavu and Goma); other zones keep their fee |
| Price | $4.99 a month or $49 a year |
| Payment | Mobile Money or cash, confirmed by staff; the membership starts at confirmation |
| Free trial | 30 days, once per account and per phone number, verified e-mail and phone required |
| Renewal | None automatic; a reminder 3 days before the end |
| End | The normal delivery fee applies again; orders already placed keep their free delivery |

How it works:
- `GET /me/membership/` gives the status (`none`, `trial`, `active`, `expired`), the plan, the end
  date, whether the trial is still available and the request waiting for payment, if any.
- `POST /me/membership/trial/` starts the trial (`trial_unavailable` with a `reason` otherwise).
- `POST /me/membership/requests/ {plan: monthly|yearly, payment_method}` asks for a paid plan at
  today's price; one request at a time, which the client can cancel.
- Staff (`membership.manage`) see the requests in `/bo/membership/requests/`, confirm one once the
  money is received or refuse it with a note; `/bo/memberships/` lists members by status.
- A confirmed period starts when the current one ends, so no day is lost. The client is notified
  when it starts, when a request is refused and before the end.
- Free delivery applies to the shipping zones an admin marks for members (Bukavu and Goma to start).

## Fidelity points

The former cashback ledger ("Cagnotte"), turned into the points ledger of the loyalty policy
("Programme de fidélité"). Its data is kept: earlier credits and spends became points movements.

| Rule | Default |
|---|---|
| Who | Every client, once an admin turns points on (`points_enabled`); no membership needed |
| Rate | 1 % (`points_percent`) of what the client really paid for the items: subtotal − coupon discount − points used, delivery excluded; rounded down to the cent. **1 point = $1** |
| Credit | Recorded when the order is delivered, **pending** until the return period is over (the site's `return_days` setting, 7 days by default), then spendable. Before delivery the invoice already shows what the order will earn, marked pending |
| Use | The client chooses how many points to use (`points`) at quote and checkout. No cap other than their available balance and the items' price after the coupon; points never pay delivery and are never paid out in cash |
| Validity | The **whole balance** stays valid while the client buys at least once every 12 months (`points_validity_months`); each order restarts the count for every point. After 12 months without an order, everything expires, pending points included |
| Returns | A cancelled or returned order loses what it still holds of its earning and gives back the points it used. Returning some units of a line takes back the share of the earning matching the real money returned (rounded down) and gives back the points spent on those units; returning or cancelling the whole order then settles only what is left |
| Scope | Online customer orders only, not resellers' in-store sales |

How it works:
- `GET /me/points/` (clients, `points.view`) gives what the client can spend
  (`available`), what waits for the return period (`pending`), the date the whole balance expires
  without a new order (`next_expiry`), whether points can be used now (`eligible`), the end of the
  closing period when the programme was switched off (`closes_at`), the count and total of
  their delivered orders (`orders_count`, `orders_total`) and their last 30 movements (`history`:
  `kind` `earn`, `spend`, `refund`, `reversal` or `expiry`, `amount`, `at`, `order_number`, and
  `pending` for an earning still in the return period). This is the "Mes points" page.
- The quote (`POST /checkout/quote/`) returns `points_available` (what the client could use on
  these items) and, for the `points` asked, the points applied (`points`), lowered to what is
  available. `POST /orders/` takes the same `points` field but refuses an amount above what is
  available with `points_unavailable` (409) — the balance changed since the quote — instead of
  lowering it silently; the client checks the amount and confirms again.
- Spending uses the oldest spendable credits first. An order shows what it used (`points`) and,
  once delivered, what it earned (`points_earned`, after any line returns).
- The invoice PDF prints a "Points de fidélité utilisés" line in the totals and a
  **"Vos points de fidélité"** statement: points earned on this invoice (marked "en attente" while
  pending), points used on it, available balance, total and count of the client's delivered orders
  ("factures encaissées"). The pending delay printed is the site's `return_days`. The statement is
  left out once points can no longer be used; during the closing period an undelivered order shows
  0 earned.
- A daily task expires the balances of clients whose latest order (not cancelled) — or latest
  credit, if later (points given back on a cancelled order, or a first credit before any order) —
  is older than the validity period.
- When an admin turns points off (`points_disabled_at` is stamped), nothing new is earned but
  clients **keep using their balance for 3 months** (`closes_at`, loyalty policy); after that the
  balance can no longer be used. Turning points back on ends the closing period.
- Like coupons, points lower what the client pays but not the sales recorded for resellers'
  commissions; they are **non-real money** (§4, *Line amounts*).

Settings (`/bo/loyalty/settings/`): `points_enabled` (off by default), `points_percent` (0.01–50,
default 1.00), `points_validity_months` (1–60, default 12). The cashback settings for members only,
the maximum share of the order and the minimum balance are gone. `GET /settings/public/` returns
them under `programmes.points` (`enabled`, `percent`, `validity_months`).

## Mobile app

The "Téléchargez notre app" block shows only once an App Store or Play Store link is set. No link is
sent by SMS.

## Status

Settings, membership and points are live. Each stays hidden until an admin turns it on. The paid
membership (Celebobo Plus) is untouched for now; it is removed in step 4.2 of the implementation
plan. Referral points for resellers (0.3 %) and Cagnotte campaigns come later.

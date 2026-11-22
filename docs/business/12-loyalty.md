# 12. Loyalty programmes

Fidelity points, **off until an admin turns them on**, and the mobile app links. Every rule below is
a setting an admin edits in `/bo/loyalty/settings/` (`loyalty.manage`); `GET /settings/public/`
returns them under `programmes` (`points`, `app_links`), and the shop only shows what is enabled.

There is no paid membership: Celebobo Plus (a paid subscription with free delivery, trial and
staff-confirmed payments) was removed in November 2026 before any client subscribed. Its endpoints,
settings, permissions, notifications and the "free delivery for members" zone flag are gone.

## Fidelity points

The former cashback ledger ("Cagnotte"), turned into the points ledger of the loyalty policy
("Programme de fidélité"). Its data is kept: earlier credits and spends became points movements.

| Rule | Default |
|---|---|
| Who | Every client, once an admin turns points on (`points_enabled`) |
| Rate | 1 % (`points_percent`) of what the client really paid for the items: subtotal − coupon discount − points used, delivery excluded; rounded down to the cent. **1 point = $1** |
| Credit | Recorded when the order is delivered, **pending** until the return period is over (the site's `return_days` setting, 7 days by default), then spendable. Before delivery the invoice already shows what the order will earn, marked pending |
| Use | The client chooses how many points to use (`points`) at quote and checkout. No cap other than their available balance and the items' price after the coupon; points never pay delivery and are never paid out in cash |
| Validity | The **whole balance** stays valid while the client buys at least once every 12 months (`points_validity_months`); each order restarts the count for every point. After 12 months without an order, everything expires, pending points included |
| Returns | A cancelled or returned order loses what it still holds of its earning and gives back the points it used. Returning some units of a line takes back the share of the earning matching the real money returned (rounded down) and gives back the points spent on those units; returning or cancelling the whole order then settles only what is left |
| Scope | Online customer orders only, not resellers' in-store sales |
| Retention | The points history goes with the account: deleted when the account is anonymised, 3 years after the client's last activity, or 3 years after the client deleted the account ([§2](02-accounts.md#inactive-accounts-retention)). Expiry lines and referral points do not count as the client's activity |

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
  0 earned. It is also left out when the client's account was deleted or anonymised: the points
  history is gone, and recomputing it would show today's rate as pending.
- A daily task expires the balances of clients whose latest order (not cancelled) — or latest
  credit, if later (points given back on a cancelled order, or a first credit before any order) —
  is older than the validity period.
- When an admin turns points off (`points_disabled_at` is stamped), nothing new is earned but
  clients **keep using their balance for 3 months** (`closes_at`, loyalty policy); after that the
  balance can no longer be used. Turning points back on ends the closing period.
- Like coupons, points are **non-real money** (§4, *Line amounts*): an order that used any points
  earns its reseller **no commission at all** (§5, rules of 16 Nov 2026).

Settings (`/bo/loyalty/settings/`): `points_enabled` (off by default), `points_percent` (0.01–50,
default 1.00), `points_validity_months` (1–60, default 12). The cashback settings for members only,
the maximum share of the order and the minimum balance are gone. `GET /settings/public/` returns
them under `programmes.points` (`enabled`, `percent`, `validity_months`, `referral_percent`,
`referral_months`).

## Referral points

Resellers' share of what their invited clients buy (reseller policy, §3.3). They are points like any
other: same balance, same "Mes points" page (`GET /me/points/`, `kind` `referral` and
`referral_reversal`), spent the same way on the reseller's own purchases, never paid in cash and never
used for delivery. Referral lines carry **no order number** (`order_number: null`; the page shows
"Commande d'un invité"): with it the reseller could work back each invitee's purchase total
(privacy policy §4). They show the kind, the date and the amount only.

| Rule | Default |
|---|---|
| Who | The reseller who invited the client (`invited_by`), while that reseller is still an active reseller. Points must be on (`points_enabled`) |
| Window | Orders the client **places** within 12 months (`referral_months`) of joining the reseller (`invited_at`: signing up with the code, or adding the code to the profile later). Clients invited before this rule count from their sign-up date |
| Rate | 0.3 % (`referral_percent`) of the items' price, delivery excluded, **rounded to the nearest cent** as in the policy's examples ($149 → 0.45 point, $389 → 1.17 points). Whether the client orders through their reseller or alone on the site |
| Non-real money | **Nothing** on an order that used points or a coupon (owner rule: any non-real money cancels the referral on the whole order). Sale prices are real money |
| Credit | On delivery, pending until the return period is over (like the client's own earning), once per order. The client still earns their own 1 % |
| Returns | A cancelled or returned order takes back what is left of the referral; returning some units of a line takes back the share matching the real money returned (rounded down) |
| Validity | Referral points follow the 12-month rule of the reseller's balance, counted from the reseller's **own** latest purchase (or own credit); referral credits restart nothing. A reseller who never bought counts from the latest referral credit |

Settings: `referral_percent` (0.01–10, default 0.30), `referral_months` (1–60, default 12).

## Mobile app

The "Téléchargez notre app" block shows only once an App Store or Play Store link is set. No link is
sent by SMS.

## Status

Settings and points are live, referral points with them; points stay hidden until an admin turns
them on. The paid membership (Celebobo Plus) is removed. Cagnotte campaigns come later.

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

## Cashback ("Cagnotte")

| Rule | Default |
|---|---|
| Who | Celebobo Plus members only (`cashback_members_only`, on by default); everyone when turned off |
| Rate | 3 % of the amount paid for the products, after coupons, deals and the cashback used, delivery excluded |
| Credit | Pending once the order is delivered, available once the return period is over; a return or cancellation takes it back |
| Use | A "Cagnotte" line at checkout, up to 50 % of the products, from a $1 balance; never paid out in cash |
| Expiry | 12 months after the credit |
| Scope | Online customer orders only, not resellers' in-store sales |

How it works:
- `GET /me/cashback/` gives what the client can spend (`available`), what waits for the return
  period (`pending`), the next expiry and whether they qualify (`eligible`).
- The quote (`POST /checkout/quote/`) returns `cashback_available`; with `use_cashback: true` it
  applies it as a "Cagnotte" line (`cashback`), and `POST /orders/` takes the same flag.
- Spending uses the credits that expire first. An order shows what it used (`cashback`) and, once
  delivered, what it earned (`cashback_earned`); the invoice prints the "Cagnotte" line.
- A cancelled or returned order gives back what it used and loses what it earned.
- A daily task expires credits left unused after their validity.
- Like coupons, the cashback lowers what the client pays but not the sales recorded for resellers'
  commissions.

## Mobile app

The "Téléchargez notre app" block shows only once an App Store or Play Store link is set. No link is
sent by SMS.

## Status

Settings, membership and cashback are live. Each stays hidden until an admin turns it on.

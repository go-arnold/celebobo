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

## Cashback ("Cagnotte")

| Rule | Default |
|---|---|
| Rate | 3 % of the amount paid for the products, after coupons and deals, delivery excluded |
| Credit | Pending once the order is delivered, available once the return period is over; a return or cancellation takes it back |
| Use | A "Cagnotte" line at checkout, up to 50 % of the products, from a $1 balance; never paid out in cash |
| Expiry | 12 months after the credit |
| Scope | Online customer orders only, not resellers' in-store sales |

## Mobile app

The "Téléchargez notre app" block shows only once an App Store or Play Store link is set. No link is
sent by SMS.

## Status

The settings are live. Cashback and membership are built next, in that order; until then their
switches stay off.

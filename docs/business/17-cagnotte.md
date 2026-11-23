# 17. Cagnotte operations

Loyalty policy, « Cagnotte : des bonus en plus de vos points ». Time-limited operations that come
**on top of** the 1 % fidelity points (§12), never instead of them. App `apps/cagnotte`.

## The operations

| Kind | What the client gets | When | Fidelity points |
|---|---|---|---|
| Remise immédiate (`discount`) | x % off the products concerned | At checkout | 1 % of what is really paid (100 $ − 10 % → 0.90 point) |
| Cashback (`cashback`) | x % of what was really paid for the products concerned, as **points** or by **Mobile Money** (M-Pesa, Airtel Money) | After delivery, once the trial is over | 1 % as usual |
| Points majorés (`boosted_points`) | x % extra points | After delivery, once the trial is over | 1 % as usual |

The policy's « cadeau » (a gift) is handed over by staff and is not managed here.

## Conditions

Each operation sets, and the site shows (`GET /cagnotte/current/`):
- **dates**: start and end. **One operation at a time**: periods may touch but not overlap
  (`campaign_overlap`).
- **products concerned**: categories (a top-level category covers its sub-categories) and/or
  products; none chosen means **every product**.
- **minimum purchase** on the products concerned (optional): below it, nothing.
- **cap** per order (optional).
- **cashback payout**: points or Mobile Money. Boosted points are always points.
- **validity of Cagnotte points**: 1 to 730 days (default 90) from the day they become spendable.
- a free text with the conditions as announced.

Percent: 0.01 to 50. An operation paid in points needs fidelity points on (`points_disabled`).
Once an operation has **started**, its conditions are fixed (`campaign_started`): staff can only
end it early (`POST /bo/campaigns/{id}/end/`). An upcoming one can be changed or deleted.

The terms of an order are those of the operation **running when it was placed** (`campaign_id`
and `campaign_name` on the order).

## Immediate discount

- The quote (`POST /checkout/quote/`) and the order show `campaign_name`, `campaign_kind`,
  `campaign_percent` and `campaign_discount`. The order's `discount` **includes** the Cagnotte
  discount; a coupon applies to what is left (10 % coupon on 300 $ with a 20 $ Cagnotte discount →
  28 $).
- The discount belongs to the lines concerned (`campaign_discount` on each line); a price changed by
  the reseller keeps the line's share.
- Like a coupon it is **non-real money** (§4, *Line amounts*): the order earns its reseller no
  commission and no referral points (§5, owner rule of 16 Nov 2026).
- For a cashback or boosted points, the quote gives an estimate (`campaign_advantage`), computed
  on the products' price; the final amount is computed on delivery from what was really paid.

## Cashback and boosted points

- Computed on **delivery**, on what the client really paid for the products concerned (after the
  coupon, points and store credit), then the minimum and the cap.
- **Pending** until the trial is over (the site's `return_days`, 7 days), like the 1 % points.
- **In points**: a `cagnotte` line in the points history (§12, `GET /me/points/`), spendable like
  any point, then expiring on its **own date** (`expires_at`), outside the 12-month rule; the daily
  points task expires them. The invoice prints « Points Cagnotte gagnés sur cette facture ».
- **By Mobile Money**: staff (`cagnotte.pay`) list what is due (`GET /bo/cagnotte/rewards/?due=1`:
  client, order, phone, amount) and record each transfer with its reference
  (`POST /bo/cagnotte/rewards/{id}/pay/`, `reward_not_due` before the end of the trial or once
  paid). The client is told (« Cashback versé »).
- A cashback or boosted points don't make the order non-real money: commission and referral points
  are due as usual.
- The client sees their advantages in `GET /me/cagnotte/` (operation, order, amount after returns,
  status, date).

## Returns

- Units returned: the advantage is computed again on what is left (below the minimum, nothing)
  and the difference is taken back: Cagnotte points reversed (`cagnotte_reversal`), a cashback not
  yet sent lowered.
- Order cancelled or returned whole: the advantage is cancelled.
- A Mobile Money cashback **already sent** cannot be taken back automatically: it shows as
  `owed_back` on the reward, and staff deduct it from the refund (policy: « déduit du
  remboursement »).

## Who does what

| Endpoint | Who |
|---|---|
| `GET /cagnotte/current/` | everyone (the running operation or `null`) |
| `GET /me/cagnotte/` | the client (`cagnotte.view.own`) |
| `GET/POST /bo/campaigns/`, `GET/PUT/DELETE /bo/campaigns/{id}/`, `POST …/end/` | admin (`cagnotte.manage`) |
| `GET /bo/cagnotte/rewards/`, `POST …/{id}/pay/` | manager+ (`cagnotte.pay`) |

Back-office: « Cagnotte » (operations for admins, « Cashbacks à verser » for managers). Shop: a
banner with the running operation and its conditions; the checkout shows the Cagnotte discount or
the expected advantage.

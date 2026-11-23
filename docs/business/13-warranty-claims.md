# 13. Warranty claims

The warranty and returns policy (`apps/content/policies/garantie-et-retours.md`) gives each product
three protections. A client claims on **one unit of an order line** of a delivered order; staff
handle the claim step by step. App `apps/warranty`.

## Which protection covers a claim

| Kind (`kind`) | Window | Possible outcomes |
|---|---|---|
| `defect` — faulty or different from the order | the **7-day trial** (art. 59), then the **one-month CeLE BoBO warranty**, both from the delivery | repair, exchange, refund |
| `change_of_mind` — the product does not suit | the **7-day trial** only, product as new; the client pays the return | exchange, or store credit valid 6 months (§14) |
| `counterfeit` | **12 months** from the purchase (authenticity guarantee) | refund, delivery included |

- The windows are domain constants (`apps/warranty/domain/rules.py`). The claim records the
  protection that covered it (`trial`, `warranty`, `authenticity`).
- A **repair extends the warranty** of that line by the days the product spent in repair (from the
  reception to the end of the repair).
- An **exchanged** product keeps the warranty left on the old one, **15 days at least**
  (`exchange_warranty_until`).
- **Sealed only**: a product marked `sealed_return_only` (in-ear earphones; §3) is taken back for a
  change of mind only if its seal is intact, checked at the reception (`seal_required`). Defects
  stay covered.

## Submitting (client, `claims.submit.own`)

- `GET /me/orders/{id}/claimable/` — each line of the client's order: the kinds it can still be
  claimed for, the end of the trial and of the warranty, the end of the authenticity guarantee, and
  an open claim if any. The client's order page offers « Faire une réclamation » once delivered.
- `POST /me/claims/` (`Idempotency-Key`) `{order_id, item_id, kind, description, serial, photos}`:
  - only the client's own delivered (or partly returned) orders, on a line not fully returned
    (`line_not_claimable`);
  - when the line has serial numbers, the claimed unit's **serial must be one of them**, as on the
    invoice (`serial_not_on_order`);
  - one open claim per line at a time (`claim_already_open`);
  - outside every window: `claim_window_closed`;
  - up to 6 photos, uploaded first as message attachments.
- `GET /me/claims/`, `GET /me/claims/{id}/` — the client's claims and their steps (« Mes
  réclamations »).

## Handling (staff, `claims.manage`)

| Step | Endpoint | Rule |
|---|---|---|
| 1. Answer | `POST /bo/claims/{id}/answer/` `{return_method, note}` | **within 72 hours** (art. 65; `answer_due`): drop-off at the shop (avenue Mwanga n° 21, Bukavu) or pick-up by the reseller |
| 2. Reception | `POST /bo/claims/{id}/receive/` `{sealed, note}` | the drop-off slip is the claim number (`RC-00012`) and the reception date; a client may walk in before any answer. Diagnosis due **3 working days** later (Monday–Saturday) |
| 3. Diagnosis | `POST /bo/claims/{id}/diagnose/` (`Idempotency-Key`) `{covered, outcome, note, new_serial, quote}` | the outcome must fit the kind (`outcome_not_allowed`): **repair** → in repair, due within **10 working days**; **exchange** → closed, with the new unit's serial; **store credit** (change of mind) → closed, the unit is returned through the order's line return and what the client paid for it becomes store credit valid 6 months (§14); **refund** → closed, the unit is returned through the order's line return (stock, points taken back, refund due recorded on the order, to pay **within 15 days**); **not covered** → closed, product given back, optional quote for a paid repair |
| 4. Repair done | `POST /bo/claims/{id}/repaired/` `{note}` | closes the claim; the warranty runs as many more days as the repair took |

- Steps come in order (`claim_step_not_allowed`).
- `GET /bo/claims/?status=…` lists the claims (« Réclamations » in the back-office); each claim says
  whether its current step is **overdue** (answer, diagnosis or repair past its deadline).

## Notifications

- A new claim notifies staff (« Nouvelle réclamation RC-… »).
- Each step tells the client what happens next (e-mail always sent): how to bring the product
  back, the drop-off slip, the diagnosis, the outcome (refund within 15 days, exchange ready, repair
  done with the warranty extended, not covered with the quote).

## Not covered yet

- The delivery fee is refunded for a defective product (policy) — the line return refunds the
  product only; staff refund the fee by hand for now.

# 15. Cash collected by resellers

Reseller policy, section 6: the reseller who delivers often collects the payment. That money belongs
to Celebobo until it is remitted, **in full, by Mobile Money, within 24 hours**; the reseller does
not deduct their commission (it is paid separately, §5). The unremitted cash a reseller may hold is
**capped by their level** (section 9). App `apps/cash`.

## Collections

- When an order assigned to a reseller becomes **paid**, or at the latest **delivered**, its total is
  a **collection** owed by that reseller, due **24 hours** later. Once per order.
- A **pickup** order is paid at the shop: no collection.
- An order **cancelled** before any remittance owes nothing (the reseller gave the money back to the
  client); once partly remitted, staff settle it by hand.

## The cap and the block

| Level | Unremitted cash allowed |
|---|---|
| Débutant | 300 $ |
| Confirmé | 1 000 $ |
| Ambassadeur | 2 500 $ |

Levels come with step 7.5; until then every reseller counts as **Débutant**.

A reseller gets **no new orders** (`reseller_cash_blocked`, 422, `meta.reason`) while:
- some collected money is **more than 24 hours** old and not remitted, or
- the cash they hold **reaches their cap**.

The assignment screen shows why (`cash_blocked` on each assignable reseller) and greys them out.

## Remittances (staff, `cash.manage`)

`POST /bo/cash/remittances/` (`Idempotency-Key`) `{reseller_id, amount, reference, received_at}`:
the money the reseller handed over (Mobile Money reference). It settles the **oldest collections
first**; never more than the reseller holds (`remittance_exceeds_held`); only to a reseller
(`not_a_reseller`). Recorded with who received it. Event `CashRemitted` (audit).

## Who sees what

| Endpoint | Who | Content |
|---|---|---|
| `GET /bo/cash/summary/` | reseller (own, `cash.view.own`) / staff (`?reseller_id=`) | held, overdue, cap and level, why blocked, the collections still owed (due dates), the last remittances |
| `GET /bo/cash/` | staff | every reseller who holds cash, blocked ones first |

Back-office: « Encaissements » (staff: the list and « Enregistrer un reversement »; reseller:
« Argent à reverser »).

The demo data remits each reseller's collections as it goes, so demo resellers are never blocked.

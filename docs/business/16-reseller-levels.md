# 16. Reseller levels and sanctions

Reseller policy, sections 9 and 10. App `apps/standing`.

## Levels

| Level | Validated sales, last 3 months | Rating | Advantages |
|---|---|---|---|
| Débutant | — | — | Orders in their zone. Cash cap 300 $ |
| Confirmé | 1 000 $ or more | 4.0 or more | Priority in their zone. Cash cap 1 000 $. Demo product lent |
| Ambassadeur | 3 000 $ or more | 4.5 or more | Early access to promotions. Cash cap 2 500 $. Featured on the site |

- **Validated sales**: valid sales, older than **7 days** (past the withdrawal period), minus what
  was refunded, made in the **3 months** before the review.
- **Rating**: the average of the clients' ratings of the reseller (§4). Without any rating yet, a
  reseller stays **Débutant**.
- Both thresholds must be met. A level can go **down** as well as up.
- The **review** runs on the **first day of each quarter** (1 January, April, July, October), by a
  daily task (`standing.review_levels`) that does nothing on other days. Staff can run it at any
  time (`POST /bo/standing/review/`, « Revoir les niveaux »).
- A changed level is notified to the reseller (« Nouveau niveau : … »).
- The level sets the **cash cap** (§15) at once.

## Sanctions

| Kind | Effect | Before it applies |
|---|---|---|
| Avertissement écrit | Written warning, kept on the record | Applies at once |
| Suspension (7 to 30 days) | **No new orders** until it ends (`reseller_suspended`, 422, `meta.until`) | 48 hours to explain |
| Exclusion | The reseller account is **closed** | 48 hours to explain |

Steps:

1. Staff open a sanction (`POST /bo/sanctions/`, `Idempotency-Key`, `{reseller_id, kind, reason,
   days, urgent}`). The reseller is told in writing (notification and e-mail, always sent) with the
   reason.
2. For a suspension or an exclusion, the reseller may **explain in writing within 48 hours**
   (`POST /bo/sanctions/{id}/explain/`, from « Mon niveau »). After 48 hours:
   `explanation_closed`.
3. Staff **decide** (`POST /bo/sanctions/{id}/decide/`, `{apply, note}`): apply it once the
   reseller explained or the 48 hours are over (`hearing_pending` before that), or drop it at any
   time. A decided sanction cannot change (`sanction_closed`).

An **urgent** case (money diverted) applies at once, without waiting for an explanation.

While suspended, a reseller is greyed out on the assignment screen (« Suspendu jusqu'au … »,
`suspended_until` on each assignable reseller). Orders already assigned stay theirs.

## Who sees what

| Endpoint | Who | Content |
|---|---|---|
| `GET /bo/standing/` | reseller (own, `standing.view.own`) / staff (`?reseller_id=`) | level and advantages, sales and rating at the last review, what the next level needs, suspension end, sanctions |
| `POST /bo/standing/review/` | staff (`standing.manage`) | runs the review now, returns how many levels changed |
| `GET /bo/sanctions/` | staff | every sanction (`?reseller_id=`, `?status=notified|applied|dropped`) |

Back-office: « Mon niveau » (reseller) and « Niveaux et sanctions » (staff).

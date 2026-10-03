# 6. Resellers

## Becoming a reseller

### 1. Application (public)

`POST /reseller-applications/` — anyone, logged in or not (rate-limited).
First name, last name, email, phone, city, message.

- Refused if the email already belongs to a reseller (`already_reseller`) or already has an
  application **under review** (`application_pending`).
- The applicant receives an acknowledgement email; staff see the new application live.

### 2. Review (staff, `reseller_applications.review`)

`/bo/reseller-applications/` (filter by status, search).

- **Approve** (optional commission rate and manager): the application's email is **onboarded** as a
  reseller (below) and the application is closed as approved. The applicant receives a welcome email
  (with an invitation to set a password if the account was just created).
- **Reject** with a reason: closed as rejected, the applicant is emailed.
- An application can be decided **once** (`application_reviewed`).

### Onboarding rules

| Situation for that email | Result |
|---|---|
| No account | A reseller account is created (invitation email to set a password). |
| Existing **client** | The account is upgraded to reseller (it keeps its history). |
| Deactivated reseller | Reactivated. |
| Active reseller | Refused (`already_reseller`). |
| Manager or admin | Refused (`staff_cannot_become_reseller`). |

The reseller gets: a **referral code** (4 digits, unique, kept forever), availability `offline`, the
commission rate given (default **7 %**), and optionally a **manager** (must be an active staff member,
`invalid_manager`).

Admins can also turn an existing user into a reseller by **changing their role** (§2), or create a
reseller account directly from the user screen.

## Reseller management (staff, `resellers.manage`)

`/bo/resellers/` — search, active/inactive filter, ordering (name, newest, oldest, most invitees,
highest rate). Each reseller shows: contact, referral code, rate, availability, manager, join date,
last seen, number of invitees and cumulative **performance** (sales count, revenue, commission earned
and due).

- **Change** commission rate (0–50 %) and manager.
- **Deactivate / activate**: a deactivated reseller cannot log in and is no longer assignable.
- `/bo/resellers/stats/`: totals (resellers, active, invited clients, pending applications) and the
  **top reseller** over the last 30 days.
- `/bo/resellers/{id}/invitees/`: the clients who signed up with their code.

## The reseller's own space

| What | Endpoint |
|---|---|
| Dashboard: own sales figures, open orders, commission due | `/bo/dashboard/*` (scoped to themselves) |
| Orders assigned to them | `/bo/orders/` |
| Their sales, recording and conversion | `/bo/sales/`, `/bo/orders/{id}/convert-to-sales/` |
| Their commissions and payouts | `/bo/commissions/summary/`, `/series/`, `/bo/payouts/` |
| Referral kit | `/bo/me/referral/` |
| Their invitees (with orders count and amount ordered) | `/bo/me/invitees/` |
| Availability | `PATCH /bo/me/availability/` |

### Referral kit

- **Code**: 4 digits. Clients enter it at sign-up or once later in their profile (§2).
- **Link**: `{FRONTEND_URL}/inscription?code={code}` — the sign-up form is pre-filled.
- **QR code** of the link, a ready-made **share text** and a **WhatsApp** share link.

### Availability and presence

- A reseller sets **online**, **away** or **offline**. Staff see it in the assignment list and next
  to orders; changes are pushed in real time (`presence.changed`).
- Separately, the WebSocket keeps a **live presence** (connected users, refreshed every ~90 seconds);
  staff can query who is online (`/bo/presence/`, `presence.view`).

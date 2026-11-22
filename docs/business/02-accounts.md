# 2. Accounts

## Sign up (client)

`POST /auth/register/` — first name, last name, email, password; optional phone and referral code.

- The email is normalised (trimmed, lower-cased) and must be unique (`email_already_used`).
- The phone, if given, must be unique (`phone_already_used`).
- The password must pass Django's validators: at least 8 characters, not too similar to the
  name/email, not a common password, not only digits (`weak_password`).
- A **referral code** must belong to an active reseller (`unknown_referral_code`). The new client is
  then permanently linked to that reseller (an "invitee"); `invited_at` records when, since referral
  points run for 12 months from then (§12, *Referral points*). Whatever the date, while that
  reseller stays active, staff assigning the client's orders see them as the **suggested reseller**
  ([orders](04-cart-checkout-orders.md#assignment)).
- Every self-registered account is a **client**.
- **Email verification is mandatory**: a link to `/verifier-email/{key}` is emailed; logging in
  before confirming the address is refused. The link can be re-sent (`POST /auth/email/resend/`).

## Log in / sessions

- `POST /auth/login/` with email + password. Tokens are httpOnly cookies: access token
  (15 minutes) and refresh token (14 days, rotated on every refresh, the old one blacklisted).
- **Lockout**: 5 failed attempts → login blocked for 15 minutes (`too_many_login_attempts`).
- A deactivated account cannot log in (`inactive_account`); deactivation revokes its tokens.
- **Google sign-in**: the frontend sends the OAuth `code`; the backend exchanges it, creates the
  account if needed (client, email already verified by Google) and opens the session.
- **Forgot password**: `POST /auth/password/reset/` emails a link to
  `/reinitialiser-mot-de-passe?uid=…&token=…`. The answer is the same whether or not the email exists.
- **Change password** (logged in): old password + new password twice.

## Profile

`GET/PATCH /me/` — first name, last name, phone, avatar, referral code.

- **Avatar**: uploaded through the media flow (§10), then referenced by `avatar_upload_id`. Only the
  user's own avatar upload is accepted (`invalid_avatar`).
- **Referral code** can be added **once**, if the account has none yet (`referral_already_set`),
  and never one's own code (`self_referral`). The 12 months of referral points start then.
- The email cannot be changed by the user (an admin can, see below).

## Address book

`/me/addresses/` — label (home / work / other), recipient, phone, street, quarter, city, country.

- At most **20 addresses** (`address_book_full`).
- The first address becomes the **default**; another can be made default at any time.
- Deleting the default address promotes another one to default.
- At checkout the chosen address is **copied** into the order: later edits do not change past orders.

## Delete my account

`DELETE /me/` — **clients only** (`staff_account_deletion` for resellers and staff).

The account is **anonymised**, not erased, so orders and sales keep their history:
email → `deleted-{id}@deleted.invalid`, names, phone and avatar cleared, password made unusable,
account deactivated, `deleted_at` set, all addresses deleted.

## Download my data

"Mes données" (`/compte/donnees`) — privacy policy §11, right to get one's account and order data
in a readable format (art. 211). Every signed-in user, for their **own** data only
(`personal_data.export.own`, granted to every role).

- `POST /me/data-export/` starts a background job (`202`), built like the other document jobs (§10);
  `GET /me/data-export/` returns the latest export and `available_at` (next request allowed, or
  `null`); `GET /me/data-export/{id}/download/` returns the ZIP.
- **One request per hour** per user (`personal_data_export_too_soon`, `429`, with
  `meta.available_at`); a failed export does not count.
- The **download link is valid 48 hours** after the file is ready (`job_expired` afterwards), and
  the file is deleted then (hourly purge). Only the owner can download it (`404` for anyone else);
  the back-office job routes (`/jobs/…`) never list or serve it.
- **Audit**: each request (`PersonalDataRequested`) and each download (`PersonalDataDownloaded`) is
  recorded in the business events journal, with the user as author.
- A self-service download answers the request at once (the policy's 72 h acknowledgement and 30-day
  answer still apply to written requests).

**The ZIP** holds `mes-donnees.json` (machine-readable: format `celebobo.personal-data`, version 1,
stable English keys, ISO 8601 dates, money as strings with two decimals), `mes-donnees.html` (the
same content in French, readable in a browser) and `LISEZMOI.txt`. Sections, in this order (a role
section with nothing to show is left out):

| Key | Content |
|---|---|
| `account` | Profile, e-mail (verified or not), phone, role, sign-up and last login, own referral code, who invited the user (their code and first name) and when, addresses |
| `notification_preferences` | E-mail / push choice per topic |
| `consents` | Reserved for the consent records (step 6.1) |
| `orders` | Every order: number, dates, status, items and prices (discount, points, amount paid, returns), totals, payment method, delivery (address, zone, estimate, attempts), the reseller's **name**, refund, status history, the rating given, invoice and delivery receipt references |
| `points` | Balance (available, pending, expiry) and the full movement history |
| `reviews` | Reviews written, hidden ones included |
| `favorites` | Favorite products and when they were added |
| `messages` | The user's own discussions (every message); in discussions assigned to them as a reseller, only the messages they wrote — the client's messages are the client's data. At most 5,000 messages (`truncated`) |
| `reseller_applications` | Applications sent (or that made the user a reseller), with the decision and its reason |
| `reseller` | Resellers (or anyone with sales or commissions): commission summary, own sales, commission entries, payout statements with their lines, payouts received |

Left out on purpose: other people's contact details (a reseller's phone or e-mail on an order, the
customer on a reseller's sale), the staff member who reviewed or paid, purchase costs and margins,
the delivery code (a one-time handover secret), notifications (copies of the events above), push
devices, assistant chats and the newsletter subscription.

Each app gives its part through its own selectors or facades (one collector per app, in
`apps/documents/adapters/personal_data.py`), assembled by `PersonalDataExport`; a new section is a
collector registered under its key in `register_collectors`.

## Notification preferences

See [§7](07-messaging-notifications.md#preferences).

## Staff-managed accounts (admin)

Admins manage users at `/bo/users/` (managers can only view them).

| Action | Rules |
|---|---|
| Create a user | Name, email (unique), phone (unique), role. The new user receives an **invitation email** to set a password. |
| Edit a user | Name, email, phone (uniqueness checked). |
| Change role | Not on oneself (`own_role_change`). Becoming a reseller gives the account a referral code if it has none. Manager/admin accounts are flagged `is_staff`. |
| Deactivate / activate | Not oneself (`own_account_deactivation`). Deactivation revokes all sessions. |
| Send password reset | Emails the user a reset link. |

Reseller-specific management (manager, activation) is described in [§6](06-resellers.md).

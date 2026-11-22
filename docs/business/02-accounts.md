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
account deactivated, `deleted_at` set, all addresses deleted. The newsletter subscription of the
account's e-mail is deleted too, unless that address had already unsubscribed (the opposition list
is kept, [§8](08-content.md#newsletter)). A former reseller's **referral code stays** on the
deleted account: codes are unique among accounts, so it is never issued again to someone else.

What the identity scrub leaves elsewhere (order phone, notes, delivery codes, rating comments,
points history, conversations…) goes **3 years after the deletion**, with the inactive accounts
below.

## Inactive accounts (retention)

Privacy policy §6: a client account is kept while it is active, then **3 years after the last
activity**, and anonymised. A daily task (`accounts.inactive_clients`, see
[§10](10-backoffice-tools.md#retention)) applies it.

**Last activity** = the latest of: sign-up, last login, last session renewal (refresh token), last
order placed (whatever its status), last message sent, last points movement following an order or a
return (earned, spent, refunded, taken back; an expiry or a reseller's referral points are not the
client's doing).

**Concerned**: plain client accounts only, not yet anonymised (deactivated ones included). Staff,
resellers and **former resellers** (they keep their referral code) are never touched: the
partnership and its commissions are kept 10 years for the accounts.

**Accounts the client deleted** (`DELETE /me/`) are picked up too once the deletion (their last
activity) is more than 3 years old, former resellers included (their commissions are in the sales
ledger, which is not touched). Their identity is already gone: only the erasure of what other
parts of the shop hold runs (below, from "plus its notification preferences"), with no new
`AccountDeleted` event. `personal_data_erased_at` marks every account processed — anonymised for
inactivity or erased after a deletion — so none is processed twice. A dry run lists them as
« compte client #id, supprimé le … ».

**What happens** (batches of 200 accounts, one transaction per batch and **one savepoint per
account**: an account that fails is rolled back, logged `retention.account_failed` and retried on
the next run, the others go ahead; each account is checked again under lock):
- the account as for "Delete my account" above (placeholder email, unique per account; names,
  phone, avatar cleared; deactivated; unusable password; addresses deleted; the newsletter
  subscription of its e-mail deleted unless already unsubscribed, read before the scrub), plus
  its notification preferences, its allauth e-mail addresses and Google link, its push devices,
  and its tokens blacklisted. It can no longer log in;
- its **orders stay** (10 years, OHADA) with their lines, amounts, payment and the **delivery
  recipient and address** printed on the invoice; the order phone, the client's note, the delivery
  code and the client's rating comments are cleared, the cart deleted. Staff see the client as
  « Client anonymisé », without email; the invoice shows that name in the client block and keeps
  the delivery block;
- its **points history** is deleted (the points paid on orders stay on the orders);
- its **conversations** (with their messages) and notifications are deleted;
- its **assistant conversations** (with their messages) are deleted;
- its **reseller applications** are deleted, unless approved (an approved one belongs to the
  partnership);
- its **favourites** and its **product reviews** are deleted, and the products' ratings computed
  again. The policy keeps no review beyond the account, and a review kept without its author could
  not be told apart from a made-up one: deleted rather than kept anonymously;
- last, the **files it uploaded** for itself (avatar, message attachments) that nothing points to
  any more are destroyed at the storage (Cloudinary) and their records deleted; a storage failure
  rolls the account back for a retry the next day;
- invoices regenerated later for its orders (kept 10 years) leave out the **points statement**: the
  points history is gone and would be recomputed at today's rate
  ([§12](12-loyalty.md#fidelity-points));
- the link to the reseller who invited it (`invited_by`) is kept, for the reseller's commission
  history; sales, commissions and statements are untouched.

An `AccountDeleted` event (`inactivity: true`, no author) is written to the audit log per account.

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

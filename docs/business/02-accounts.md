# 2. Accounts

## Sign up (client)

`POST /auth/register/` — first name, last name, email, password; optional phone and referral code.

- The email is normalised (trimmed, lower-cased) and must be unique (`email_already_used`).
- The phone, if given, must be unique (`phone_already_used`).
- The password must pass Django's validators: at least 8 characters, not too similar to the
  name/email, not a common password, not only digits (`weak_password`).
- A **referral code** must belong to an active reseller (`unknown_referral_code`). The new client is
  then permanently linked to that reseller (an "invitee").
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
  and never one's own code (`self_referral`).
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

Reseller-specific management (commission rate, manager, activation) is described in [§6](06-resellers.md).

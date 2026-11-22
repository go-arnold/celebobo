# 2. Accounts

## Sign up (client)

`POST /auth/register/` — first name, last name, email, password, phone; optional referral code;
the consent boxes `accept_terms`, `accept_hosting_abroad` and `accept_marketing` (see *Consents* below).

- The email is normalised (trimmed, lower-cased) and must be unique (`email_already_used`).
- The **phone is required** (`phone_required`), must be a DRC mobile number (`invalid_phone`) and
  unique: **one account per phone** (`phone_already_used`). See *Phone number* below.
- The password must pass Django's validators: at least 8 characters, not too similar to the
  name/email, not a common password, not only digits (`weak_password`).
- A **referral code** must belong to an active reseller (`unknown_referral_code`). The new client is
  then permanently linked to that reseller (an "invitee"); `invited_at` records when, since referral
  points run for 12 months from then (§12, *Referral points*). The reseller's own list of invitees
  shows only the name, sign-up date and that period, never the e-mail or purchases
  ([resellers](06-resellers.md#their-invitees)). Whatever the date, while that
  reseller stays active, staff assigning the client's orders see them as the **suggested reseller**
  ([orders](04-cart-checkout-orders.md#assignment)).
- `accept_terms` and `accept_hosting_abroad` must both be ticked (`consent_required`, with one
  field error per missing box); `accept_marketing` is optional and never pre-checked.
- Every self-registered account is a **client**.
- **Email verification is mandatory**: a link to `/verifier-email/{key}` is emailed; logging in
  before confirming the address is refused. The link can be re-sent (`POST /auth/email/resend/`).

## Log in / sessions

- `POST /auth/login/` with email + password. Tokens are httpOnly cookies: access token
  (15 minutes) and refresh token (14 days, rotated on every refresh, the old one blacklisted).
- **Lockout**: 5 failed attempts → login blocked for 15 minutes (`too_many_login_attempts`).
- A deactivated account cannot log in (`inactive_account`); deactivation revokes its tokens.
- **Google sign-in**: the frontend sends the OAuth `code`; the backend exchanges it, creates the
  account if needed (client, email already verified by Google) and opens the session. A new Google
  account has given no consent yet: it goes through the **completion step** (below).
- **Forgot password**: `POST /auth/password/reset/` emails a link to
  `/reinitialiser-mot-de-passe?uid=…&token=…`. The answer is the same whether or not the email exists.
- **Change password** (logged in): old password + new password twice.

## Profile

`GET/PATCH /me/` — first name, last name, phone, avatar, referral code. The phone follows the rules of
*Phone number* above.

- **Avatar**: uploaded through the media flow (§10), then referenced by `avatar_upload_id`. Only the
  user's own avatar upload is accepted (`invalid_avatar`).
- **Referral code** can be added **once**, if the account has none yet (`referral_already_set`),
  and never one's own code (`self_referral`). The 12 months of referral points start then.
- The email cannot be changed by the user (an admin can, see below).

## Phone number

Privacy policy §2: the phone is a required field. It is how the reseller-deliverer, the payment and
WhatsApp reach the client.

- **Required for clients and resellers** (sign-up, profile, staff creating or editing such an account,
  reseller onboarding); staff accounts (managers, admins) may have none. A client or reseller cannot
  remove it (`phone_required`). Staff editing a client or reseller who has **no phone yet** (cleared by
  the migration below) may leave it empty: the account is asked for one at login, in the completion
  step; a phone typed there is still checked.
- **Normalised to E.164**: `+243` followed by the 9 digits of the national number. Accepted inputs:
  `+243 81 234 5678`, `00243812345678`, `243812345678`, `0812345678`, `812345678`, with any spaces,
  dots, dashes or parentheses, and with the trunk `0` kept after the country code (`+243 0812345678`,
  `+243 (0)81 234 5678`). Only ASCII digits count (Arabic-Indic or fullwidth digits are refused, so a
  number has one stored form). Only mobile numbers are accepted (national number starting with 8 or 9);
  anything else is `invalid_phone`. The rule lives in one small domain module
  (`apps/accounts/domain/phone.py`), mirrored by the site's form validation.
- **Unique**: one account per phone, whatever the format typed (`phone_already_used`), backed by a
  database constraint on non-empty numbers. Anonymised accounts have no phone. Two requests taking the
  same number at the same moment: the constraint refuses the second one, answered with the same
  `phone_already_used` error.
- A reseller application stores the normalised phone; approving it gives that phone to the new
  reseller account (or to an existing account that had none). An application sent **before numbers
  were checked** may hold a number that is not a DRC mobile: it is approved anyway, the reseller
  account is created without a phone and asked for one at login (completion step), and the
  application keeps the number as typed for staff to read. Applications are not rewritten by the
  migration.
- Staff searching users, resellers or applications can type the number in any accepted format, or
  part of it in the national form: `081234` finds `+243812345678`.

**Existing data** (migration `0005_phone_number_e164`): every stored number is normalised. A number
that is not a DRC mobile is cleared. When several accounts share a number, the **most recently active**
account keeps it (latest of last seen, last login and sign-up date; on a tie, the newest account) and
the others are cleared. Clients and resellers left without a phone, and accounts opened with Google
(Google gives no phone), are asked for one in the completion step.

## Consents

Privacy policy §3, §5 and §8 (Code du numérique art. 68–70, 192, 196, 202). Each consent is its own
record, kept as proof:

| Consent (`kind`) | What the person accepts | Required |
|---|---|:-:|
| `terms` | Conditions of sale and processing of personal data | yes |
| `hosting_abroad` | Express consent to the hosting of the data outside the DRC (Germany, United States) | yes |
| `marketing` | Commercial offers by SMS, WhatsApp or e-mail | no |

- A record holds the **version** of the document accepted, `accepted_at`, `withdrawn_at` and how it was
  given (`source`: `signup`, `account`, `google` for the completion step right after a Google
  sign-up; `checkout` is reserved for a box on the checkout page, none yet).
- The version comes from the content app (`SiteContentFacade.policy_versions`): `terms` refers to
  the **conditions of sale** page (`conditions-de-vente`), `hosting_abroad` and `marketing` to the
  **privacy policy** page (`politique-de-confidentialite`), which describes the hosting abroad (§5)
  and the offers (§8). A new version of a page asks again for the required consents given on it.
- History is never rewritten: accepting again (a new version) adds a record, withdrawing sets
  `withdrawn_at` on the records still open. Giving a consent already given on the current version
  records nothing. The back-office shows them read-only on the user.
- Only **clients and resellers** must give the required consents; staff accounts (managers, admins)
  are Celebobo's own team.

`GET /me/consents/` lists, per consent: `given`, the version and date of the last acceptance still
open, `current_version` of the document, `outdated` (given on an older version), plus `missing` and the
full `history`. `POST /me/consents/ {kinds: [...]}` gives consents (`source` `account`);
`DELETE /me/consents/{kind}/` withdraws one (`consent_not_found` for an unknown kind). Both answer the
updated list.

### Completion step

`GET /me/` (and the login answer) carries `missing_consents`: the required consents not given, or given
on an older version of the policy (when its version changes, everyone accepts again), and
`phone_required`: a client or reseller without a phone number. While either is set, every
authenticated endpoint answers **403 `account_incomplete`** (`meta.missing_consents`,
`meta.phone_required`), except:

- `/me/` (read, edit, and `DELETE` to close the account) and `/me/consents/`;
- login, logout, token refresh, password change, e-mail verification;
- public endpoints (catalogue, policy pages, settings), which do not need an account.

The site then shows a completion page asking for the missing consents and the phone (saved with
`PATCH /me/`). This concerns existing accounts
(created before consents were recorded), accounts opened with Google, resellers onboarded by staff and
everyone after a new policy version.

### Withdrawing

- `marketing` is withdrawn and given again in one click from the account ("Mes consentements").
- Withdrawing `terms` or `hosting_abroad` is possible, but the account can then no longer be used: the
  completion step comes back, offering to accept again or to **close the account** (`DELETE /me/`,
  clients). A reseller who withdraws must ask an administrator to deactivate the account
  (`staff_account_deletion`).
- Closing the account withdraws every consent still open.

### Newsletter and promotions

The newsletter (e-mail) follows the `marketing` consent: giving it subscribes the account's e-mail
(source `compte`), withdrawing it unsubscribes that e-mail. The unsubscribe link of a newsletter
e-mail also withdraws the account's `marketing` consent (policy §8: "STOP" stops the offers). A
subscription from the footer form alone is an e-mail-only opt-in with its own record (subscriber,
date, source): it does not create a `marketing` consent, which also covers SMS and WhatsApp.
Notifications of the `promotions` topic only reach accounts with the `marketing` consent.

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
account deactivated, `deleted_at` set, all addresses deleted. Consents still open are withdrawn
(their records stay, as proof). The newsletter subscription of the
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

## Download my data

"Mes données" (`/compte/donnees`) — privacy policy §11, right to get one's account and order data
in a readable format (art. 211). Every signed-in user, for their **own** data only
(`personal_data.export.own`, granted to every role).

- `POST /me/data-export/` starts a background job (`202`), built like the other document jobs (§10);
  `GET /me/data-export/` returns the latest export and `available_at` (next request allowed, or
  `null`); `GET /me/data-export/{id}/download/` returns the ZIP.
- **One request per hour** per user (`personal_data_export_too_soon`, `429`, with
  `meta.available_at`); after a **failed** export, a new request is allowed **10 minutes** after
  the failure. Requests of one user are serialised (a lock per user until the request is saved), so
  parallel clicks start a single export.
- An export still pending or running **30 minutes** after the request was lost by the worker: it is
  shown as failed ("La préparation a pris trop de temps…") and a new request is allowed at once
  (the lost job is then marked failed). The page polls the status every 3 s the first minute, every
  10 s up to 5 minutes, then every 30 s, and stops after 31 minutes.
- The **download link is valid 48 hours** after the file is ready (`job_expired` afterwards), and
  the file is deleted then (hourly purge). Only the owner can download it (`404` for anyone else);
  the back-office job routes (`/jobs/…`) never list or serve it.
- **Audit**: each request (`PersonalDataRequested`) and each download (`PersonalDataDownloaded`) is
  recorded in the business events journal, with the user as author.
- A self-service download answers the request at once (the policy's 72 h acknowledgement and 30-day
  answer still apply to written requests).

**The ZIP** holds `mes-donnees.json` (machine-readable: format `celebobo.personal-data`, version 1,
stable English keys, ISO 8601 dates, money as strings with two decimals), `mes-donnees.html` (the
same content in French, readable in a browser) and `LISEZMOI.txt` (the 72 h / 30-day reminder and
the data-protection contact the privacy policy names, celestinbahiga@gmail.com — setting
`DOCUMENTS_PRIVACY_CONTACT`; the company contact on invoices is separate). In the HTML page, only date
fields (keys ending in `_at`, `_date` or `_on`, plus `at`, `date_joined`, `last_login`,
`next_expiry`) are shown as French dates — free text (messages, notes, reviews, addresses) is
printed as typed, and a date value that cannot be read is printed as stored. Sections, in this order (a role
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
| `messages` | The user's own discussions (every message); in discussions assigned to them as a reseller, only the messages they wrote — the client's messages are the client's data. Sender: the person's name, "Celebobo" for automatic messages, "Compte supprimé" when the author's account was deleted. At most 5,000 messages (`truncated`) |
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
| Create a user | Name, email (unique), phone (normalised, unique; required for clients and resellers), role. The new user receives an **invitation email** to set a password. |
| Edit a user | Name, email, phone (normalised, uniqueness checked; a client's or reseller's phone cannot be removed, but may stay empty when the account has none yet). |
| Change role | Not on oneself (`own_role_change`). Becoming a reseller gives the account a referral code if it has none. Manager/admin accounts are flagged `is_staff`. |
| Deactivate / activate | Not oneself (`own_account_deactivation`). Deactivation revokes all sessions. |
| Send password reset | Emails the user a reset link. |

Reseller-specific management (manager, activation) is described in [§6](06-resellers.md).

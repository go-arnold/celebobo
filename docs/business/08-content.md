# 8. Site content

## Home page

`GET /home/` (public) returns, in one call: the active **banners** grouped by placement, the **deal
of the day**, the featured **brands**, the **sections** laid out by staff, **deals** (products on sale),
**new arrivals**, **best sellers**, and each visible **category with some of its products**.
Public content is cached and refreshed automatically when content or categories change.

## Banners, pages, FAQ (`content.manage`, staff)

| Item | Fields and rules |
|---|---|
| **Banner** | Title, subtitle, image (`banner` upload), link URL and label, position, active flag, optional start/end dates (end must follow start, `invalid_schedule`). Only active banners within their dates are shown. A **placement** says where it goes: `hero` (carousel, the default), `hero_mini`, `hero_side`, `deal_side`, `showcase:<category>` or `column:<category>`. It can point to a **product** (must be visible, `banner_product_unavailable`): the shop then shows the product's real price and link. A small **eyebrow** ("Audio", "Nouveau") and a **tone** (`light` image with dark text, `dark` image with light text) complete it. The order is set per placement. |
| **Home section** | `/bo/home-sections/`: a category shown as a large block (`showcase`) or a column (`column`), with an optional title (the category name otherwise), active flag and order (`POST reorder/ {ids}`). The home page returns each active section with the category's best sellers and its sub-categories. The category must be visible (`section_category_unavailable`). |
| **Page** (CMS) | Slug (unique, `slug_taken`), title, summary, body (Markdown: headings, lists, tables, bold, links), published flag, position, and for a policy its **version** and **effective date** (`effective_on`), shown above the text. Shop URL `/pages/{slug}`. Demo seed: `a-propos`, `guide`, `conditions`, `retours`. |
| **FAQ** | Question, answer, category (groups the FAQ page), position, published flag. |

Unpublished pages and FAQ entries are visible only in the back-office.

Back-office: « Pages et politiques », « FAQ » (questions grouped by category, add, edit, hide, delete).

**Policies.** The conditions of sale and the five policies are pages, loaded once by a migration from
`apps/content/policies/*.md` (a page that already exists is never overwritten), then edited in the
back-office: `conditions-de-vente` (0.9, migration `content/0008_conditions_of_sale`; the `terms`
consent is given on it), `politique-de-confidentialite` (0.9.2), `politique-de-livraison` (0.9.2), `garantie-et-retours`,
`programme-de-fidelite`, `politique-revendeurs` (0.9.2). The site footer links to them. When a policy
changes, staff update its text, version and effective date together.

The reseller policy went from 0.9.1 to 0.9.2 to match the commission rules (50 % of the margin, nothing on
an order paid even partly with points or a coupon; see 05-sales-commissions). Migration
`content/0007_reseller_policy_0_9_2` replaces the page only if it still holds the untouched 0.9.1 text;
a page edited in the back-office is left for staff to update.

## Site settings (`settings.manage`, admin)

One record, `GET /settings/public/` exposes the public part to the shop:

| Setting | Used for |
|---|---|
| Hotline, WhatsApp, email, address, opening hours | Header, footer, contact page |
| Payment methods (subset of Orange Money, Airtel Money, M-Pesa, cash) | Choices offered at checkout (`unknown_payment_method`) |
| Social links | Footer |
| USD → CDF rate | Showing prices in Congolese francs |
| Newsletter code and discount (%) | Code given to new subscribers |
| Return period (days, 7 by default) | "Retours sous x jours" wherever the shop promises it |
| Support open 24/7 (yes by default) | "Service client 24/7" in the header, opening hours otherwise |
| Shipping summary (from the zones) | "Free shipping from $…" messages |

## Contact form

`POST /contact/` — anyone (rate-limited). Name, email, phone, subject, message.

- A hidden **honeypot** field: if a bot fills it, the message is stored as `spam` and nobody is notified.
- Otherwise the sender gets an acknowledgement email and staff see the message live in the
  **contact inbox** (`contact.inbox`), where they mark it `handled` (or `spam`) with an internal note.
  The inbox shows counts per status. Back-office: « Messages de contact » (new / handled / spam,
  subject filter, search; reply by email or phone, then « Marquer traité »).
- Retention: a contact message is a message with customer service, which the privacy policy (§6)
  keeps "3 years after the last order". The form is open to visitors without an account or order,
  so the period runs from the message: it is deleted **3 years after it was received**, whatever
  its status, by a daily task (`content.contact_messages`, see
  [§10](10-backoffice-tools.md#retention)).

## Newsletter

- `POST /newsletter/subscribe/` — anyone, with the source (footer, checkout…). Subscribing again
  with an active email is harmless (`already_subscribed`).
- A new subscriber receives a **welcome email** with the newsletter **coupon code** and discount.
- Every email contains an **unsubscribe link** (`/newsletter/desinscription?token=…`); an unknown token
  answers `unknown_subscription`.
- Staff (`newsletter.view`) list subscribers (active / unsubscribed, search) and export them as CSV
  (back-office « Newsletter »; the export keeps the filters).
- The newsletter follows an account's `marketing` consent, both ways: giving it subscribes the
  account's e-mail, withdrawing it unsubscribes it, and the unsubscribe link withdraws the consent
  ([accounts](02-accounts.md#newsletter-and-promotions)).
- Retention (privacy policy §6: marketing consent lasts until withdrawn, or 3 years without
  interaction): an **active** subscriber whose last (re)subscription is more than 3 years old is
  deleted by a daily task (`content.stale_subscribers`, see [§10](10-backoffice-tools.md#retention)).
  Subscribing again after unsubscribing restarts the period (`subscribed_at` is reset); subscribing
  again while still subscribed does not. The newsletter records no other interaction yet (no opens
  or clicks); the account marketing consents will add theirs. **Unsubscribed** addresses are kept:
  they are the opposition list (« ne plus m'écrire »).
- When a client deletes their account, or it is anonymised for inactivity, the subscription of its
  e-mail is deleted, unless that address had already unsubscribed: an opposition the person
  expressed stays ([§2](02-accounts.md#delete-my-account)).

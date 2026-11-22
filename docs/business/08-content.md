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

**Policies.** The five policies are pages, loaded once by a migration from `apps/content/policies/*.md`
(a page that already exists is never overwritten), then edited in the back-office:
`politique-de-confidentialite` (0.9.2), `politique-de-livraison` (0.9.2), `garantie-et-retours`,
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
  The inbox shows counts per status.

## Newsletter

- `POST /newsletter/subscribe/` — anyone, with the source (footer, checkout…). Subscribing again
  with an active email is harmless (`already_subscribed`).
- A new subscriber receives a **welcome email** with the newsletter **coupon code** and discount.
- Every email contains an **unsubscribe link** (`/newsletter/desinscription?token=…`); an unknown token
  answers `unknown_subscription`.
- Staff (`newsletter.view`) list subscribers (active / unsubscribed, search) and export them as CSV.
- The newsletter follows an account's `marketing` consent, both ways: giving it subscribes the
  account's e-mail, withdrawing it unsubscribes it, and the unsubscribe link withdraws the consent
  ([accounts](02-accounts.md#newsletter-and-promotions)).

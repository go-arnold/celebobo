# 8. Site content

## Home page

`GET /home/` (public) returns, in one call: the active **banners**, **deals** (products on sale),
**new arrivals**, **best sellers**, and each visible **category with some of its products**.
Public content is cached and refreshed automatically when content or categories change.

## Banners, pages, FAQ (`content.manage`, staff)

| Item | Fields and rules |
|---|---|
| **Banner** | Title, subtitle, image, link URL and label, position, active flag, optional start/end dates (end must follow start, `invalid_schedule`). Only active banners within their dates are shown. |
| **Page** (CMS) | Slug (unique, `slug_taken`), title, summary, body, published flag, position. Shop URL `/pages/{slug}`. Seeded: `a-propos`, `guide`, `conditions`, `retours`. |
| **FAQ** | Question, answer, category (groups the FAQ page), position, published flag. |

Unpublished pages and FAQ entries are visible only in the back-office.

## Site settings (`settings.manage`, admin)

One record, `GET /settings/public/` exposes the public part to the shop:

| Setting | Used for |
|---|---|
| Hotline, WhatsApp, email, address, opening hours | Header, footer, contact page |
| Payment methods (subset of Orange Money, Airtel Money, M-Pesa, cash) | Choices offered at checkout (`unknown_payment_method`) |
| Social links | Footer |
| USD → CDF rate | Showing prices in Congolese francs |
| Newsletter code and discount (%) | Code given to new subscribers |
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

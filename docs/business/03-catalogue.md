# 3. Catalogue

## Categories

Managed by staff (`categories.manage`) at `/bo/categories/`.

- Fields: name (unique, `category_name_taken`), description, icon (one of `mobile`, `monitor`,
  `tablet`, `headphone`, `watch`, `game`, `flash`, `camera`, `printer`, `keyboard`), image, visible
  in the shop or not, position.
- The **slug** (URL) is derived from the name; shop URLs use it: `/categorie/{slug}`.
- **Order**: staff send the full list of ids in the wanted order (`/bo/categories/reorder/`).
- **Hidden** categories (and their products) disappear from the shop but stay in the back-office.
- **Delete**: refused while the category still has products (`category_not_empty`) unless a
  destination category is given (`?move_to=`): products are moved first, then the category is deleted.

## Products

Managed by staff (`products.manage`) at `/bo/products/`. Resellers can read the back-office list
(`products.view`) to record sales.

| Field | Rules |
|---|---|
| Name, short description | Description 10–255 characters. |
| Long description, features, care instructions, delivery policies | Free text. |
| Category | Required. |
| `price` | > 0. |
| `sale_price` (promotion) | Optional; must be > 0 and **lower than** `price` (`invalid_pricing`). The shop shows the discount %. Bulk "discount" sets it from a percentage (max 90 %). |
| `cost_price` (purchase price) | Optional, ≥ 0. **Never shown to clients.** Used for profit and margin. |
| Badge | none, `new` ("Nouveauté") or `best_seller` ("Best-seller"). During its first **20 days** a product always displays `new`, whatever badge was chosen. |
| Free shipping / own shipping fee | Overrides the zone fee for this product (see §4). |
| Stock threshold | Below or at this level the product is "low stock" (default 5). |
| `sell_by` | "Should be sold before" date; cannot be in the past (`sell_by_in_past`). |
| Visible in the shop | Inactive products stay in the back-office only. |
| Images | Uploaded first (§10), then attached by id. Saving `image_ids` **replaces the whole gallery**. |

- The **slug** comes from the name; shop URLs use it: `/produits/{slug}`.
- **Trash**: deleting a product moves it to the trash (soft delete). It disappears from the shop and
  can be **restored**. There is no permanent delete through the API.
- **Duplicate**: copies a product into a new one named "… (copie)", **hidden** and with **stock 0**,
  ready to be edited before publishing.
- **Bulk actions** on a selection: activate, deactivate, trash, restore, change category, set a
  discount %, clear the discount.

### Variants

A product can declare **options** (e.g. `Couleur: Noir, Bleu`, `Stockage: 128 Go, 256 Go`) and
**variants** (one combination each).

- Each option needs a unique name and at least one value (`invalid_variant_attributes`).
- A variant must give **exactly one value for every option** (`invalid_variant_attributes`); two
  variants cannot share the same combination (`duplicate_variant`); SKUs are unique (`duplicate_sku`)
  and generated if not given.
- A variant may have its own price (otherwise the product price applies) and its own image.
- **When a product has variants, stock is managed per variant** (`variants_manage_stock`); the
  product stock is the sum of its variants.
- In the shop, a product with variants must be bought with a variant chosen (`variant_required`).

## Stock

Every stock change is a **movement** with a reason, a signed quantity, the resulting balance, the
author and a note (history at `/bo/products/{id}/stock-movements/`).

| Reason | When |
|---|---|
| `inventory` | Initial stock at creation, or inventory count |
| `restock` | Goods received |
| `correction` | Manual correction, sale deletion, product form edit |
| `loss` | Breakage / loss |
| `return` | Returned goods (order return, sale return) |
| `order` | Stock **reserved when an order is placed**, released if it is cancelled |
| `sale` | Stock taken by a sale recorded directly |

- Manual adjustments (`stock.adjust`): **add/remove** a quantity or **set** the stock to a value.
- Stock can never become negative (`negative_stock`); an order or sale that needs more than what is
  available is refused (`insufficient_stock`, with the available quantity).
- **Low stock**: when a product or variant falls to its threshold, a `stock.low` alert is pushed to
  staff in real time. `/bo/stock/alerts/` lists everything currently low.

## Shop display

- Only **active** products in **visible** categories, not in the trash, are shown.
- **Badge**: `new` automatically for the first 20 days, then the badge chosen by staff.
- **Rating**: average of **published** reviews.
- **Low stock**: shown when `0 < stock ≤ threshold`. Out of stock products remain visible but cannot be added.
- **Sorting**: relevance, newest/oldest, price ↑/↓, best sellers, best rated, name.
- **Filters**: category, price range, on sale, in stock, badge, explicit ids. Facets give counts.
- **Search** uses PostgreSQL full text in French, accent-insensitive; the search bar offers up to 6 suggestions.
- **Related products**: up to 8 from the same category first.

## Reviews

- Only a client who has **received** the product (an order containing it reached **delivered**) can
  review it (`review_not_allowed`). `GET …/reviews/eligibility/` tells the shop whether to show the form.
- **One review per client per product**: posting again updates the existing review.
- Reviews are marked **"verified purchase"**.
- Staff (`reviews.moderate`) can **hide** or re-publish a review; hidden reviews are not shown and
  don't count in the rating.

## Favorites

Logged-in users add or remove visible products (`/me/favorites/`). Product cards carry `is_favorite`.

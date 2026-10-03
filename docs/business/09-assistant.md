# 9. AI assistant

A shopping assistant available to **everyone**, logged in or not (`assistant.chat`).

## What it does

- Answers in French, briefly, about products, prices, availability, delivery and how to order.
- For anything about products it **must search the catalogue** (tool `search_products`: free-text
  query + optional category, on-sale and maximum-price filters) and answer **only from the results** —
  it never invents a product, price or stock. Results come back as **product cards** linking to
  `/produits/{slug}`.
- Search is semantic: products are indexed as embeddings, refreshed automatically whenever a product
  or category changes. Admins can rebuild the whole index (`embeddings.reindex`).
- Facts it states: prices in US dollars, delivery in 24–48 h in Kinshasa. When it doesn't know, it
  says so and suggests contacting the team.
- Replies are **streamed** word by word.

## Sessions and memory

- A conversation is a **session**. Anonymous visitors get a session too, but cannot list past sessions.
- Logged-in users keep their sessions (`assistant.history`): list, reopen, delete.
- The assistant remembers the last 8 messages and a running **summary** (updated every 6 messages:
  needs, budget, products discussed, decisions).

## Limits

| Limit | Value |
|---|---|
| Question length | 1,000 characters (`question_too_long`) |
| Answers per day (whole shop) | 2,000 (`assistant_quota_exceeded`, until the next day) |
| Search results per answer | 6 |
| Tool calls per answer | 2 |

If the AI provider fails, the API answers `assistant_unavailable`. Without an AI key the backend runs
an **offline** mode (keyword answers) so the shop keeps working.

## Logs (staff, `assistant.logs`)

Every question/answer is logged with tokens used, estimated **cost**, and an automatic **sentiment**
(positive / neutral / negative) and **topic** (e.g. "prix", "livraison"). Staff can filter the logs
and see usage statistics.

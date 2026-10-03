# 7. Messaging, notifications and real time

## Conversations

| Kind | Created | Participants |
|---|---|---|
| **Order thread** | Automatically when an order is placed | The client; the assigned reseller joins on assignment and leaves if they decline. Staff can see every thread. |
| **Support thread** | By a client (`conversations.open_support`) with a first message | The client; staff; optionally a reseller assigned to it by staff. |

**Who sees what**: staff see all conversations; a reseller sees the ones assigned to them (and their
own as a client); a client sees their own.

### Messages

- Text and/or one image attachment (uploaded first, purpose `message_attachment`, ≤ 5 MB).
  An empty message is refused (`empty_message`).
- A message sent with a `client_msg_id` is **deduplicated**: retrying the same send never creates a duplicate.
- **System messages** are added automatically (reseller joined, discussion closed/reopened,
  proposal sent/answered…).
- **Read receipts**: `POST …/read/` marks messages read up to a point; unread counts are per user.
- **Typing** indicators travel over the WebSocket only.
- Nothing can be posted in a **closed** conversation (`conversation_closed`).

### Closing

- An **order thread is closed automatically** when its order becomes delivered, cancelled or returned.
- Back-office participants (`conversations.moderate`) can close and reopen a conversation manually.
- Staff can **assign a support thread** to a reseller (`conversations.assign`); order threads follow
  the order's assignment instead (`not_a_support_conversation`).

### Price proposals (order threads only)

1. The reseller in charge (or staff) proposes a new unit price for one line of the order
   (`price.adjust`), with a reason. Conditions: order thread (`not_an_order_conversation`), open
   conversation, order **assigned or confirmed**, price > 0 and ≤ catalogue price.
   A new proposal for the same line **supersedes** the previous pending one.
2. The proposal appears as a card in the thread; the **client of the order only** accepts or refuses
   it, once (`proposal_already_answered`).
3. **Accepted** → the order line, subtotal and total are updated (see §4). **Refused** → nothing changes.
   The proposer is notified either way.

## Notifications

Every notification is stored **in the app** (bell / notifications page) and may also be sent by
**email** and **push**, depending on the recipient's preferences. Links point to the right frontend page.

| Event | Recipients | Topic | Link |
|---|---|---|---|
| New order | All active staff | order assigned | `/admin/commandes/{id}` |
| Order assigned | The reseller | order assigned | `/admin/commandes/{id}` |
| Assignment declined | All active staff | order assigned | `/admin/commandes/{id}` |
| Order status changed | The client, and the reseller (except for the assignment itself); never the person who made the change | status changed | `/compte/commandes/{number}` |
| New message | Every other participant — at most **one unread alert per conversation** at a time | new message | `/messages/{id}` |
| New support thread | All active staff | new message | `/admin/messages/{id}` |
| Support thread assigned | The reseller | order assigned | `/admin/messages/{id}` |
| Price proposed | The client | status changed | `/messages/{id}` |
| Proposal accepted/refused | The proposer | status changed | `/admin/messages/{id}` |

Notifications can be marked read one by one or all at once; `/notifications/unread-counts/` returns
unread notifications and unread conversations (also pushed live as `unread.counts`).

### Preferences

`/me/notification-preferences/` — per **topic** and **channel** (email, push). In-app notifications
are always kept.

| Topic | Email (default) | Push (default) |
|---|:-:|:-:|
| Order assigned | on | on |
| Status changed | on | on |
| New message | on | on |
| Promotions | on | **off** |

### Push notifications

- The browser subscribes with the VAPID public key (`/push/public-key/`) and registers the device
  (`/me/devices/`). Up to **10 devices** per account (`too_many_devices`).
- A push contains title, body, link and tag; it expires after 24 h if undelivered.
- A device that fails **5 times** in a row is removed automatically.

## Real time (WebSocket)

- Logged-in users connect to `/ws/` with a **one-time ticket** (`POST /auth/ws-ticket/`); the origin
  must be an allowed frontend origin.
- Each user automatically receives their own events; staff also receive staff-wide events; a client
  subscribes to the conversations they open.
- Events pushed: new message, typing, read, conversation closed/reopened/assigned, notification
  created, unread counts, order placed/assigned/status changed/repriced, availability/presence,
  low stock, sale created/updated/deleted, commission and payout updates, new reseller application,
  new contact message, job finished, dashboard refreshed.
- Clients can send up to ~20 messages in a burst (then ~2 per second).
- A `presence.ping` every 30 seconds keeps a user "online" (expires after ~90 seconds of silence).

# telegram_gateway

The one door to Telegram. Anything in the workbench that has something worth waking the operator for sends it
here; the model can send one too, through the tool surface. A package of the workbench since stage 4 of
`one-process-per-security-boundary`, mounted under **`/telegram`** — port 8100 is nobody's now — with its own
database `telegram` and two surfaces: the REST contract and `/telegram/mcp`. The operator drives the REST half
from the terminal's **Telegram** tab (`telegram-bots-from-the-terminal`).

```bash
# from modules/workbench
uv run alembic -c alembic-telegram.ini upgrade head   # the process runs it itself too
uv run pytest tests/telegram                           # anything needing a database skips without Docker
```

## What it does not do

**It does not remember what it sent.** There is no queue, no retry and no message table. A caller
gets back what Telegram said and decides what to do with it. That is a choice, and the price is
named rather than hidden: deduplication and retry belong to the caller, and "did that alert
arrive?" is a question this module cannot answer.

The shape that pays for it is worth copying: a caller records its own *already told* marker
**after** a successful send. A failed send leaves no marker, so the caller's next pass tries
again — which is the whole retry mechanism this system has.

What it *does* remember is **that a purpose was used** — a name and when, never a text.

## Who hears what: purposes and assignments

A producer does not say who to tell. It says **what kind of event this is** — a *purpose*, an open dotted name:
`social.post.<author>`, `youtube.film.<channel>`, and whatever a rule the operator sets up tomorrow
invents (`market.price.eurusd`). The operator assigns purposes to recipients in the terminal:

- an assignment key is a purpose, a **prefix of one cut at a dot** (`youtube` catches `youtube.film.anything`, not
  `youtubers`), or `*` for everything nothing else caught; the **longest matching key wins**, `*` last;
- one key has at most one recipient (the primary key says so), and a change holds from the next message;
- a purpose nobody hears answers **`409` with `code: "unassigned"`** — not a fault, and the producer's cue to leave its
  marker unset, so what waited is announced the pass after somebody is assigned (inside each producer's own limits);
- a recipient or a bot that is still somebody's recipient **cannot be removed**: the route refuses and names the keys
  first, and `ON DELETE RESTRICT` holds when a route forgets.

`ALERT_DESTINATION` used to decide this for everybody. It now only seeds the `*` assignment, once, at start, from a
recipient that already exists — and is retired in the deploy after the one that proves it.

## What each surface publishes

| REST | |
|---|---|
| `POST /messages` | one message, now — to a destination by name **or** to whoever hears a purpose (exactly one of the two) |
| `GET /purposes` · `PUT /purposes/{name}` | what has been used or announced, and who hears it; announcing one with a description before its first event |
| `GET /assignments` · `PUT` / `DELETE /assignments/{key}` | which key goes to which recipient |
| `GET /bots` · `POST /bots/adopted` · `POST /bots/created` · `POST /bots/{username}/token` · `DELETE /bots/{username}` | the bots this gateway may speak as — adopted from a pasted token, created or rotated through the creator bot, removed |
| `GET /destinations` · `POST /destinations` · `DELETE /destinations/{name}` | who can be written to, and the start link that binds one |
| `GET /account` · `POST /account/login` · `/login/code` · `/login/password` · `DELETE /account` | the dedicated account that owns the bots |
| `GET /state` | the account, whether bots can be created, how many bots and recipients, whether `*` is assigned, how many known purposes nobody hears |
| `GET /` · `GET /ping` · `GET /health` | the deploy probe, liveness, and the database |

At `/mcp` there are **two** tools: `send_telegram_message` and `telegram_destinations`. Creating a
bot, deleting or rotating one, logging the account in, binding a destination and assigning a purpose are REST-only, and
that is the boundary worth stating: a message can be taken back by saying the next thing, while a bot, a session and an
assignment outlive the conversation that asked for them.

**No response carries a bot token or the account's session**, including the response to the request that created
them. `Bot` and `BotCredential` are separate types for that reason — the read has no token to give — and
`store.credential_of` and `store.encrypted_session` are the only statements in the module that select a secret.

## Who calls it

The conversation and the teams call the two tools as functions (`workbench/local_tools.py`). The post archive and the
YouTube archive call `POST /messages` with a purpose through the gateway's own application, as
this process (`workbench/telegram_client.py`). From outside, two applications are admitted to the REST contract, and only
those (`TELEGRAM_REST_CALLER_APPLICATION_IDS`): the operator's `az`, and the terminal, which is where the account is logged
in and purposes are assigned. The workbench's root record (`workbench/root_access.py`) refuses both everywhere else.

## Telegram has two surfaces, and they are not two flavours of one thing

**The bot surface** (`api.telegram.org/bot<token>`) is stateless, authorised by a bot token, and
sends messages. **MTProto** is a client protocol and needs a *user* identity. Creating a bot means
talking to Telegram's creator bot — an ordinary bot on a chat — so it lives only on the second
side. **No API creates a bot.**

That is why there is an **owner account**: a Telegram user account, **dedicated to the bots and never the operator's
own**, logged in from the terminal (phone → code → password only if it has one). Its session is the only credential to
Telegram's other half, so:

- it is stored in `account_session`, **encrypted with `TELEGRAM_SESSION_KEY`** (Fernet); the key lives in the server's
  environment and never in the database, so a nightly dump alone opens nothing;
- a key that is not a Fernet key refuses startup by name; a missing one only refuses *logging in* — **their absence is a
  working configuration**: the module sends, and says in `/state` what it lacks;
- a session the key no longer opens, or that Telegram ended from the phone, is a *state* (`needs_login`), found out on use
  and remembered — not a crash;
- logging out ends the session at Telegram and forgets it here, and forgets it here even when Telegram cannot be reached;
- it is used for logging in and out and for the creator-bot conversation, and for nothing else. Sending never travels the
  account session: a notification sent as a user is indistinguishable from one the user wrote.

## Three platform limits the design cannot argue with

**A bot cannot speak first.** A destination only exists once a human has opened the conversation.
The module shortens that to one tap: it issues `t.me/<bot>?start=<nonce>` (the terminal shows it as a link and a QR code
it draws itself), watches `getUpdates`, and binds the chat when that nonce comes back. It cannot be shortened to zero.

**One account may hold 20 bots** (`MAX_BOTS`). Checked before the module speaks to the creator bot,
because a refusal after the fact still costs an attempt counted against the account.

**Rate limits are roughly 30 messages a second overall and one per second per chat.** With no
queue here, a `429` reaches the caller with Telegram's own `retry_after` in it.

## Why `getUpdates` and not a webhook

A webhook would be cheaper and is the obvious shape for FastAPI. The edge rules it out: Telegram holds no Entra
identity, so its POST would be refused before this module saw it, and making it work would mean a path that accepts
*content* from the internet without a token. Long-polling needs none.

## Configuration

The workbench's `.env.example` is the list: `TELEGRAM_DATABASE_URL`, and everything else under `TELEGRAM_`, except the
application credentials `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` (from my.telegram.org, **made by the dedicated account**,
given together or not at all) and `TELEGRAM_SESSION_KEY`, whose names predate the prefix. `TELEGRAM_DATABASE_POOL_SIZE`
is 4 rather than the usual 10 on purpose: eight logical databases share one PostgreSQL whose connection budget is counted
in `scripts/tests/test_pool_budget.py`, and this work is one HTTP call per message rather than a query per row of a screen.

## Setting it up (the operator, once)

1. A **new Telegram account** for this, with its own number you will keep and two-step verification on. From it, make an
   application at my.telegram.org.
2. In the GitHub environment `vps`: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` and `TELEGRAM_SESSION_KEY`
   (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`), then deploy.
3. In the terminal's **Telegram** tab: *Zaloguj konto…* (phone, the code from the Telegram app, the password), then
   *Utwórz bota…* and *Aktywuj odbiorcę…* — scan the QR code **from the account that should receive the alerts** and press
   Start; the dialog notices. (No account? *Dodaj token…* adopts a bot made by hand with @BotFather.)
4. Assign: `*` to your recipient first, so nothing is ever collected and told to nobody, then refine by prefix.

Rolling back is clearing the assignments: the producers collect and decide exactly as before and say nothing.

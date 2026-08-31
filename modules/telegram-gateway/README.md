# telegram-gateway

The one door to Telegram. Any module that has something worth waking the operator for sends it
here; the model can send one too, through the tool surface. Port **8100**, own database
`telegram`, two surfaces in one process — the REST contract and `/mcp`.

```bash
uv run alembic upgrade head
uv run uvicorn telegram_gateway.app:app --reload --port 8100
uv run pytest          # unit; anything needing a database skips without Docker
uv run pytest -m db    # integration, against a throwaway PostgreSQL
ruff check . && uv run pyright
```

## What it does not do

**It does not remember what it sent.** There is no queue, no retry and no message table. A caller
gets back what Telegram said and decides what to do with it. That is a choice, and the price is
named rather than hidden: deduplication and retry belong to the caller, and "did that alert
arrive?" is a question this module cannot answer.

The shape that pays for it is worth copying: a caller records its own *already told* marker
**after** a successful send. A failed send leaves no marker, so the caller's next pass tries
again — which is the whole retry mechanism this system has.

## Telegram has two surfaces, and they are not two flavours of one thing

**The bot surface** (`api.telegram.org/bot<token>`) is stateless, authorised by a bot token, and
sends messages. **MTProto** is a client protocol and needs a *user* identity. Creating a bot means
talking to Telegram's creator bot — an ordinary bot on a chat — so it lives only on the second
side. **No API creates a bot.**

That is why `TELEGRAM_API_ID` / `_API_HASH` / `_SESSION` exist, why they are a credential to a
personal Telegram account, and why **their absence is a working configuration**: without them the
module sends and refuses to create, naming what is missing. Sending never travels the account
session even when it is configured — a notification sent as the operator is indistinguishable from
one the operator wrote, and it spends a private account's rate budget.

## Three platform limits the design cannot argue with

**A bot cannot speak first.** A destination only exists once a human has opened the conversation.
The module shortens that to one tap: it issues `t.me/<bot>?start=<nonce>`, watches `getUpdates`,
and binds the chat when that nonce comes back. It cannot be shortened to zero.

**One account may hold 20 bots** (`MAX_BOTS`). Checked before the module speaks to the creator bot,
because a refusal after the fact still costs an attempt counted against the account.

**Rate limits are roughly 30 messages a second overall and one per second per chat.** With no
queue here, a `429` reaches the caller with Telegram's own `retry_after` in it.

## Why `getUpdates` and not a webhook

A webhook would be cheaper and is the obvious shape for FastAPI. Easy Auth rules it out: Telegram
holds no Entra identity, so its POST is rejected by the platform before this module sees it. Making
it work would mean exempting that path — a third hole beside `/` and `/ws/stream`, and the first one
that accepts *content* from the internet. Long-polling needs none.

## Configuration

`.env.example` is the list. `DATABASE_USER` unset selects local mode and narrows the module to
loopback; set, it names the Postgres role and the credential becomes an Entra token fetched per
connection. `DATABASE_POOL_SIZE` is 4 rather than the usual 10 on purpose: seven logical databases
share one `B_Standard_B1ms` whose `max_connections` is 35, and this module's work is one HTTP call
per message rather than a query per row of a screen.

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

## What each surface publishes

| REST | |
|---|---|
| `POST /messages` | one message to a named destination, now |
| `GET /bots` · `POST /bots/adopted` · `POST /bots/created` · `DELETE /bots/{username}` | the bots this gateway may speak as — adopted from a pasted token, or created through the creator bot |
| `GET /destinations` · `POST /destinations` · `DELETE /destinations/{name}` | who can be written to, and the start link that binds one |
| `GET /state` | whether bots can be created, how many there are, how many destinations receive |
| `GET /` · `GET /ping` · `GET /health` | the deploy probe, liveness, and the database |

At `/mcp` there are **two** tools: `send_telegram_message` and `telegram_destinations`. Creating a
bot, deleting one and binding a destination are REST-only, and that is the boundary worth stating:
a message can be taken back by saying the next thing, while a bot outlives the conversation that
asked for it and still counts against the account's ceiling.

**No response carries a bot token**, including the response to the request that created it. `Bot`
and `BotCredential` are separate types for that reason — the read has no token to give — and
`store.credential_of` is the only statement in the module that selects one.

## Who calls it

Three callers, and the two lists in `caller_access.py` keep them apart. The `workbench` reaches
`/mcp` (`TELEGRAM_MCP_URL` / `_SCOPE`, the fifth pair of that shape). `social-data` and `strategy`
reach the REST contract with their own managed identities, each carrying
`TELEGRAM_GATEWAY_URL` / `_SCOPE` / `ALERT_DESTINATION` — all three or none, and none of them is a
module that collects or decides exactly as before and says nothing. The split is not reading from
writing, since both surfaces send: it is that creating a bot and binding a destination are REST.

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

## Deploying it the first time

The order is the one `CLAUDE.md` calls non-negotiable — the operator's `apply` reaches the app
before the image that enforces its settings — and it has one step nothing here can do for itself.

1. **The role, then the database.** `scripts/grant-schema-ownership.sql` against `dbname=telegram`,
   after creating the principal for this App Service's managed identity. Exactly once, before the
   first deploy: the module migrates itself at startup and cannot alter what it does not own.
2. **`terraform apply`**, which creates the App Service, the Entra registration and the `telegram`
   database, and puts the workbench's `TELEGRAM_MCP_URL` in place. The first apply needs
   `-target=azurerm_linux_web_app.telegram_gateway` once, because the firewall rule reads outbound
   addresses that do not exist until the app does.
3. **Deploy**, and `deploy_probe.py` reads `/` for `"telegram-gateway"`.
4. **A bot and a destination**, through the REST contract — and this is the one step whose caller is
   a person rather than a module. There is no screen, so it is `curl` with a token from `az`, which
   the registration pre-authorizes for exactly this:

   ```bash
   TOKEN=$(az account get-access-token \
             --resource api://tradingcenter-telegram-gateway --query accessToken -o tsv)
   BASE=https://app-tradingcenter-telegram-gateway.azurewebsites.net
   JSON='Content-Type: application/json'

   # The token comes from @BotFather: /newbot, a title, a username ending in `bot`.
   curl -sS -X POST "$BASE/bots/adopted" \
        -H "Authorization: Bearer $TOKEN" -H "$JSON" \
        -d '{"token":"<from @BotFather>"}'

   curl -sS -X POST "$BASE/destinations" \
        -H "Authorization: Bearer $TOKEN" -H "$JSON" \
        -d '{"name":"operator","bot":"<the @name>"}'
   ```

   The second answers with a start link. **Somebody taps it, from the account that should receive
   the alerts**, within thirty minutes. Until that tap the gateway holds an intention rather than an
   address, and `GET /state` says `destinations_ready` is zero. Where the account session is
   configured, `POST /bots/created` replaces the first call and @BotFather is never opened by hand.
5. **Only then the callers.** Set `telegram_alert_destination` in `terraform.tfvars` to the name
   bound in step 4 and apply: `social-data` and `strategy` get their three settings and start
   announcing. Setting it earlier is not an outage — the sends are refused, nothing is marked as
   told, and each next pass tries again.

Rolling back is the same lever in reverse: clear `telegram_alert_destination`, apply, and both
callers collect and decide exactly as before while saying nothing. Their own tests walk that state.

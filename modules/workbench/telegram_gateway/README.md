# telegram_gateway

The one door to Telegram. Anything in the workbench that has something worth waking the operator for sends it
here; the model can send one too, through the tool surface. A package of the workbench since stage 4 of
`one-process-per-security-boundary`, mounted under **`/telegram`** — port 8100 is nobody's now — with its own
database `telegram` and two surfaces: the REST contract and `/telegram/mcp`.

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

Three callers, none of them over a network any more but one. The conversation and the teams call the two
tools as functions (`workbench/local_tools.py`). The post archive and the strategy platform call
`POST /messages` through the gateway's own application, as this process (`workbench/telegram_client.py`),
and `ALERT_DESTINATION` says who they tell — unset, both collect and decide exactly as before and say
nothing. The operator's `az` is the one caller from outside: `TELEGRAM_REST_CALLER_APPLICATION_IDS` is its
list alone, and the workbench's root record (`workbench/root_access.py`) refuses it everywhere else. The
split is not reading from writing, since both surfaces send: it is that creating a bot and binding a
destination are REST.

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

The workbench's `.env.example` is the list: `TELEGRAM_DATABASE_URL`, and everything else under `TELEGRAM_`,
except the account session, whose three names predate the prefix. `TELEGRAM_DATABASE_POOL_SIZE` is 4 rather
than the usual 10 on purpose: seven logical databases share one `B_Standard_B1ms` whose `max_connections` is
50, and this work is one HTTP call per message rather than a query per row of a screen.

## Binding the first bot and destination

The one step whose caller is a person rather than a program. There is no screen, so it is `curl` with a
token from `az` for the workbench's audience, which `entra.tf` (`workbench_cli`) pre-authorizes for exactly this:

```bash
TOKEN=$(az account get-access-token \
          --resource api://tradingcenter-agent --query accessToken -o tsv)
BASE=https://app-tradingcenter-agent.azurewebsites.net/telegram
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

**Only then the callers.** Set `telegram_alert_destination` in `terraform.tfvars` to the name
bound above and apply: the workbench gets `ALERT_DESTINATION` and its post archive and strategy platform start
announcing. Setting it earlier is not an outage — the sends are refused, nothing is marked as
told, and each next pass tries again.

Rolling back is the same lever in reverse: clear `telegram_alert_destination`, apply, and both
callers collect and decide exactly as before while saying nothing. Their own tests walk that state.

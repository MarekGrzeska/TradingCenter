## Context

See proposal.md — Why. Two spikes exist and each solved half the problem; this design folds
them into one service.

What the spikes established, all of it measured against a working key rather than read from
documentation. These numbers shape the design, so they are recorded here:

| Constraint | Value |
|---|---|
| Candles per request | 1000 (`1001` → `error.invalid.max`) |
| Date window width | at most `(count − 1) × resolution` (a window counts both edges) |
| `from`/`to` format | `YYYY-MM-DDTHH:MM:SS`, UTC, no zone |
| Result direction | forward from `from`, not backwards from `to` |
| Past the bottom of history | `error.prices.not-found` |
| Session lifetime | ~10 idle minutes; tokens are response *headers* |
| Streaming auth | tokens go **inside every message**, not in connection headers |
| Stream ping | at least every 10 minutes |
| Rate limit | 10 requests/second |
| `ohlc.event` frequency | 0 in 60 s on US100 at `MINUTE_5` — only on close |
| `quote` frequency | 296 in 60 s on the same instrument |
| `ohlc.event` duplication | twice per candle: `priceType` `bid` and `ask` (~1.8 pt apart on US100) |
| Deep read cost | `OIL_CRUDE` `MINUTE_5` × 20 000 → 30 requests, 26.2 s |
| History depth | `DAY` reaches 1991 on US100; `MINUTE_5` about two years |

Two facts drive most of what follows. First, the streaming credential model rules out a plain
reverse proxy — something must own the outbound connection and inject tokens per message.
Second, `ohlc.event` firing zero times in a minute means a stream carrying only closed candles
looks broken; the candle in progress has to come from somewhere else.

## Goals / Non-Goals

**Goals:**

- One process, one contract, three concerns: trade, read history, stream.
- Provider quirks confined to the adapter — a consumer never learns what `dealReference` or
  `epic` mean.
- The forming candle defined once, in the module, so every consumer sees the same candle.
- Startup fails loudly on misconfiguration rather than at the first order.

**Non-Goals:**

- No persistence. This module is a window onto capital.com, not an archive of it. A store is
  `market-data`'s job in the ecosystem, and duplicating it here would give one bar two origins.
- No provider abstraction layer. One provider, one adapter.
- No UI. A React console is a later module and consumes this one over HTTP and WebSocket.
- No live account, at any configuration.

## Decisions

### Python 3.12 + FastAPI

Chosen over Node/TypeScript and C#/.NET.

The work is almost entirely I/O concurrency: dozens of sequential HTTP pages, a persistent
outbound WebSocket, and a fan-out to subscribers. `asyncio` covers all three in one model, and
the trading half already exists in Python — the adapter, DTOs, mapping and the `respx`-mocked
tests move across close to unchanged. FastAPI publishes OpenAPI from the same pydantic models
that validate input, so the contract cannot drift from the code that serves it.

Node was the alternative with the stronger claim on the streaming half: `server/capitalPlugin.js`
is a working relay today. But adopting it means rewriting the trading half from nothing and
splitting the ecosystem across two languages for one module. C# types best and is the language
Marek knows best, but nothing in either spike would survive the port, and its real advantage —
genuine parallelism — buys nothing for a workload that is waiting on sockets.

The GIL is not a constraint here for the same reason: no step is CPU-bound.

Dependencies, all of them earning a line: `fastapi`, `uvicorn[standard]`, `httpx` (async REST),
`websockets` (outbound stream), `pydantic-settings` (config). Dev: `pytest`, `pytest-asyncio`,
`respx` (HTTP mocking), `ruff`. Tooling is `uv`.

### Layout

```
modules/capital-gateway/
  capital_gateway/
    app.py            FastAPI assembly, lifespan, error handling
    config.py         settings + the demo-only guard
    dtos.py           the contract: Instrument, Candle, Account, Position, Order, …
    errors.py         the module's error type → HTTP status
    client.py         thin async REST client: auth, tokens, one retry on 401
    adapter.py        raw capital.com payloads ⇄ DTOs; the async settlement
    mapping.py        pure functions, no I/O — testable against fixtures alone
    history.py        backwards paging past the 1000-row ceiling
    stream/
      upstream.py     one outbound connection per (epic, resolution): subscribe, ping, reconnect
      forming.py      quotes → the candle in progress. Pure, no I/O
      hub.py          rooms, fan-out, lifecycle
      messages.py     the published WebSocket message shapes
  tests/
    fixtures/         recorded provider payloads
  pyproject.toml
  README.md
```

`mapping.py` and `stream/forming.py` hold no I/O deliberately: the two places where the
provider's semantics are easiest to get wrong are the two that can be tested without a socket.

### The forming candle lives server-side

Today this logic is a React hook, so it is reachable only from a browser. Moving it into
`stream/forming.py` means an agent, a backtest and a future console share one definition of
"the current candle" instead of writing three.

The rule: a quote's timestamp is floored to the resolution to find its period. A quote in the
current period extends high/low and moves close; a quote in a later period opens a new candle.
When `ohlc.event` finally arrives, it overwrites — it saw the whole period, the module only saw
it from the moment it connected.

Arithmetic bucketing is correct only intraday. `DAY` and `WEEK` boundaries follow the venue's
session, not UTC midnight, so for those resolutions quotes extend the last known candle and only
the provider's closed candle moves the boundary. Guessing there would produce a candle that
looks right and is wrong.

### The stream carries `candle` and `quote`, not the provider's shapes

`{kind: "candle", forming: true|false, …}` is what a chart consumes — one message kind, upsert by
timestamp. `{kind: "quote", bid, ask, …}` stays alongside it because a spread is needed at
execution time and cannot wait for a candle to close. `{kind: "status"}` and `{kind: "error"}`
carry liveness.

The provider's raw `ohlc.event` is not republished: it arrives twice per candle, once per price
side, and passing both through is what makes a chart jump across the spread.

### The bid side, everywhere

REST history exposes both sides per candle edge; the stream's `classic` OHLC exposes one. Taking
bid in both places is what makes history and live data join without a step. It is a convention,
not a truth — recorded here because the seam is invisible until it is wrong.

### Deep paging anchors on data, not on the clock

Each further window is anchored on the oldest candle actually collected. A calendar-derived
cursor drifts across a weekend or a holiday, because the provider returns far fewer candles than
the window implies; anchoring on data costs one extra request instead of a gap. The loop stops on
`error.prices.not-found`, on a window that yields nothing older, or on the requested count.

A deep read is a long HTTP request — 26 s in the worst measured case. It stays a plain request
rather than a job with a polling endpoint: a job needs state, and this module has none. The
response reports the request count so the cost is visible.

### `BrokerPort` is deleted

`typing.Protocol` is structural: nothing declares that it implements the port, and only an
annotation typed as `BrokerPort` makes a checker compare them. `broker-gateway` has no such
annotation — `app.py` types its dependency as the concrete adapter — so the port is checked by
nothing today. It is a comment in the shape of a type. The DTOs stay, because they *are* the
HTTP contract. A second broker, if one ever arrives, gets its interface extracted from a working
adapter, which is mechanical.

*(In C# terms: an `interface` is nominal and the compiler enforces it; a `Protocol` is
structural and enforces nothing unless a type checker is pointed at a matching annotation.)*

### Demo-only is a startup check

`config.py` rejects any base or streaming URL that is not the demo host, before the app object
exists. A runtime guard on trading endpoints would leave a live session authenticated and
readable; refusing to start leaves nothing running to misuse.

## Risks / Trade-offs

**A deep read can outlive a client's timeout (26 s measured, worse instruments possible)** →
the response states its request count and coverage; a consumer that needs more depth asks for a
narrower range. If this becomes routine, the answer is a job with a polling endpoint, and that is
a later change.

**Concurrent deep reads can exhaust the 10 req/s budget** → provider calls pass through one
bounded gate, so a second deep read queues instead of triggering a rate-limit refusal that would
look like a data error.

**A forming candle after a restart understates its range** → it is marked `forming: true` and the
spec says so plainly. An indicator computed on it repaints; it is for looking at, not for
backtesting.

**No persistence means no history beyond what the provider keeps** → `MINUTE_5` is about two
years and nothing recovers what is past it. Accepted: archiving is a different module's job.

**Session renewal under concurrency could stampede** → one in-flight login is shared by every
waiting caller, and a 401 triggers exactly one re-login and one retry.

**The upstream connection can drop silently** → the module pings well inside the provider's
tolerance, publishes `status: reconnecting` on a drop, and reconnects while subscribers remain.

**Trading against a demo account proves less than it appears to** → fills are simulated, and
demo liquidity is not real liquidity. The module's correctness claim is about the contract, not
about execution quality.

## Migration Plan

Nothing to migrate: TradingCenter is empty and this change establishes its layout. TradingHub
keeps running untouched; `broker-gateway` there is superseded but retiring it is a separate
decision.

Rollback is deleting the module directory — the standing property that the ecosystem's module
rules exist to preserve.

## Open Questions

- Whether the WebSocket message shapes are published as a JSON Schema file in the repository or
  only documented in the README. Affects a consumer's ability to generate types, not the
  behaviour, so it can be decided when the first consumer exists.
- What the repository's own constitution says — the file that would state conventions,
  principles and the module contract for TradingCenter is not written yet, and was deliberately
  deferred rather than copied from TradingHub.

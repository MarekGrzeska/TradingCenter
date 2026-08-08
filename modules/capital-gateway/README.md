# capital-gateway

capital.com behind one contract: **trade**, **read history deeper than the provider serves
in one request**, and **watch a live feed**. Every provider quirk — session tokens, the
instrument tree, asynchronous `dealReference → confirms` settlement, the candle that only
arrives when it closes — stays inside the module.

**Demo only.** Any endpoint other than the demo host is refused at startup, so this cannot
place an order with real money.

## What

- `dtos.py` — the contract: `Instrument`, `Candle`, `CandleHistory`, `Account`, `Position`,
  `Order`, `WorkingOrder`.
- `config.py` — settings and the demo-only guard.
- `client.py` — async REST, session renewal, one shared login, one retry on 401.
- `rategate.py` — the sliding window that keeps every provider call under 10/s.
- `mapping.py` — payload → DTO. Pure, testable against fixtures alone.
- `adapter.py` — accounts, instruments, candles, trading, settlement.
- `history.py` — paging backwards past the 1000-row ceiling.
- `stream/` — `messages` (the WebSocket contract), `forming` (the candle in progress),
  `upstream` (one outbound connection), `hub` (rooms and fan-out).

## Run

```bash
cp .env.example .env      # capital.com DEMO credentials
uv run uvicorn capital_gateway.app:app --reload --port 8010
```

Swagger: <http://localhost:8010/docs>

## Test

```bash
uv run pytest                     # fixtures + respx-mocked; no network
uv run pytest --run-live          # + read-only smoke tests against the real demo API
uv run pytest --run-live-trading  # + tests that open, amend and close demo positions
uv run ruff check . && uv run ruff format --check .
```

`--run-live-trading` has its own flag because it **writes**: it opens a position, amends
it, closes it, rests an order and cancels it. Everything is cleaned up in a `finally`, but
the account will show the round trip. It is the only thing that can catch capital.com
changing a dealing rule or a payload — mocks are structurally blind to that.

## Contract

HTTP, described by OpenAPI at `/docs`.

| Method | Path | Returns |
|--------|------|---------|
| GET | `/capabilities` | `Capabilities` — provider, environment, order types |
| GET | `/accounts` | `Account[]` |
| PUT | `/accounts/active` | `Account` — switch the active account |
| GET | `/asset-classes` | `AssetClass[]` — the classes instruments are described with |
| GET | `/instruments` | `InstrumentPage` — deduped, with a `truncated` flag |
| GET | `/instruments?asset_class=` | the same, narrowed to one class |
| GET | `/instruments/search?q=` | `Instrument[]` |
| GET | `/instruments/{symbol}/candles` | `Candle[]` — one request, at most 1000 |
| GET | `/instruments/{symbol}/history` | `CandleHistory` — paged, with its cost |
| GET | `/instruments/{symbol}/history?before=` | the same, reaching back from a past instant instead of now |
| GET | `/instruments/{symbol}/history?after=` | the same, stopping at an instant — a lower bound in time, which `bars` cannot express |
| GET | `/positions` | `Position[]` |
| POST | `/orders` | `Order` — MARKET fills, LIMIT/STOP rest |
| DELETE | `/positions/{id}` | `Order` — close |
| PUT | `/positions/{id}` | `Order` — set/remove SL/TP |
| GET | `/working-orders` | `WorkingOrder[]` |
| DELETE | `/working-orders/{id}` | `Order` — cancel |

**A filtered catalogue gets a bigger budget.** The walk bounds itself by nodes visited, and
`truncated` says when that bound stopped it. Filtering by class does not make the walk cheaper —
a node's name suggests its class but does not promise it, so the sieve is on the markets and every
branch is still visited. What changes is the default bound: 300 nodes unfiltered, 1500 with a
class, because one class is a fraction of the catalogue and the same budget reaches that much
further inside it. Whoever picks an instrument to archive out of such a list is committing to tens
of minutes of backfill, and a list cut short costs them more than it costs somebody browsing.

**A filtered catalogue gets a bigger budget.** The walk bounds itself by nodes visited, and
`truncated` says when that bound stopped it. Filtering by class does not make the walk cheaper —
a node's name suggests its class but does not promise it, so the sieve is on the markets and every
branch is still visited. What changes is the default bound: 300 nodes unfiltered, 1500 with a
class, because one class is a fraction of the catalogue and the same budget reaches that much
further inside it. Whoever picks an instrument to archive out of such a list is committing to tens
of minutes of backfill, and a list cut short costs them more than it costs somebody browsing.

**A deep read reaches back from now, unless told otherwise.** `history.collect` pages backward,
each window anchored on the oldest candle the previous page actually returned. Without `before`
the first window has nothing to anchor on and asks the provider for "the newest candles" — which
is why, unqualified, a deep read always ends at the present. `before` gives that first window an
anchor of its own, so a caller can ask for a window that ended months or years ago directly,
rather than only ever reaching the part of history nearest to now.

**`after` is the other end, and it is not the same thing as `bars`.** `bars` counts *candles*.
An instrument that trades five days a week hands back `bars` candles spanning half again as much
calendar time as `bars` periods — so a caller wanting "nothing older than this moment" cannot say
it as a count, and one that tries silently collects months it never asked for. `after` says it as
a moment: windows are clamped to it so no request is spent on candles that would be thrown away,
paging stops once a page reaches it, and anything older that still arrives inside a page is
dropped. Reaching `after` is deliberately **not** `history_ended` — that flag means the provider
has nothing older, and a consumer stores it as a permanent boundary; saying it because the caller
asked for less would stop the next, deeper read ever being made.

**An answer is settled, not acknowledged.** A deal the provider has not resolved comes back
`PENDING` with its reference — never `FILLED`.

**A refusal names itself.** `REJECTED` carries the provider's `reason` — `RC_NOT_ENOUGH_MARGIN`
and the like. Note that capital.com may accept a request, hand back a reference, and only
refuse at settlement, so a `dealReference` is not an acceptance. It also assigns a `dealId`
to a deal it refuses: on a `REJECTED` order the `id` identifies the attempt, not a position.

**Amending stops is tri-state.** A number sets, `null` removes, an omitted field is left
alone, so changing one stop cannot clear the other.

### WebSocket — `/ws/stream?symbol=US100&resolution=MINUTE_5`

Not in the OpenAPI schema: OpenAPI has no vocabulary for WebSocket payloads. The shapes are
pydantic models in [`stream/messages.py`](capital_gateway/stream/messages.py).

```jsonc
{"kind":"candle","symbol":"US100","resolution":"MINUTE_5","time":1784988000,
 "open":1.0,"high":1.2,"low":0.9,"close":1.1,"volume":null,"forming":true}
{"kind":"quote","symbol":"US100","time":1784988001234,"bid":1.1,"ask":1.2}
{"kind":"status","state":"connected"}   // connecting | connected | reconnecting | closed
{"kind":"error","message":"..."}
```

`candle.time` is **epoch seconds** at the start of the period — what a chart library indexes
by. The REST side uses ISO strings; the seam is deliberate, not an oversight.

A missing symbol or an unknown resolution is refused **before** the handshake, so a bad
request fails to connect rather than handing back a socket that dies a moment later.

## What the numbers here mean

Everything below was **measured** against a working key, not read from documentation.

| | |
|---|---|
| Candles per request | 1000 (`1001` → `error.invalid.max`) |
| Window width | at most `(count − 1) × resolution` — it counts both edges |
| Deep read | `OIL_CRUDE` `MINUTE_5` × 20 000 → 30 requests, 26.2 s |
| History depth | `DAY` reaches 1991 on US100; `MINUTE_5` about two years |
| `ohlc.event` | **0** times in 60 s on US100 at `MINUTE_5` — only on close |
| `quote` | **296** times over the same minute |

That last pair is why the forming candle exists. A feed carrying only sealed candles shows a
chart standing still for five minutes while the price moves.

**The forming candle is assembled here, not by the consumer** — so a chart, an agent and a
backtest share one definition of "the current candle" instead of writing three.

**It understates its range after a restart.** The high and low reflect only quotes seen since
this module connected, until the provider's sealed candle overwrites them. It carries
`forming: true` and it is for looking at, not for backtesting: an indicator computed on it
repaints.

**Candles are the bid side, everywhere.** The stream publishes bid, so history takes bid too;
a midpoint would put a half-spread step — about 1.8 points on US100 — at every seam between
stored history and live data.

**`DAY` and `WEEK` never guess a boundary.** Flooring a timestamp to a period is exact only
while a period is a fixed number of seconds, and a daily candle starts at the venue's session
open, not UTC midnight. At those resolutions quotes extend the last known candle and only a
sealed candle moves the boundary.

**Streamed candles carry no volume.** `volume` is always `null` on the WebSocket feed —
neither the provider's candle event nor its quotes report it. The field is there so the
shape matches the REST candle, which does carry `lastTradedVolume`. A volume-based
indicator cannot be computed on this feed; read it from `/candles` or `/history` instead.

**One connection per `(symbol, resolution)`**, shared by every subscriber and closed when the
last one leaves.

**Ten requests per second, per process.** The gate lives on the client, and the app owns one
client — so two clients in one process would be two gates and twice the rate.

**Nothing is stored.** This is a window onto capital.com, not an archive of it — `MINUTE_5`
reaches back about two years and nothing recovers what is past that.

**A demo fill proves the contract, not the execution.** Fills are simulated and demo
liquidity is not real liquidity.

# market-data

The candle archive. `capital-gateway` is a window onto the provider and keeps nothing; this
module keeps what flew past it, so a chart, a backtest or an agent can read a series that
exists tomorrow as well as today.

**Behind the gateway, always.** capital.com counts its 10 requests/second against the
account, not the process, so a second client anywhere spends the same allowance twice. This
module refuses to start if either of its upstream URLs points at capital.com — the gateway
owns the single rate gate and the demo-only guard, and going around it breaks both.

## What

- `config.py` — settings, the provider-host guard, and the budgets this module may spend.
- `models.py`, `periods.py` — a candle, a coverage range, and the gateway's two spellings of
  a period start reduced to one instant.
- `db.py` — the connection string, in the two shapes asyncpg and SQLAlchemy each insist on.
- `store.py` — the only door to the candle table: closed candles in, one row per period.
- `coverage.py` — what the archive has verified, and so which absences are answers.
- `tracking.py` — which pairs are collected, and whether collection is actually happening.
- `rollups.py` — the derived resolutions, computed from the minute series and refreshed only
  where a write touched them.
- `ingest/` — the live feed, backfill, and the budget they share.
- `gateway/` — the only place that talks to `capital-gateway`: deep history over HTTP, live
  candles and quotes over its WebSocket. Paging is the gateway's job, so a fill is one request
  however deep — and genuinely long (20 000 five-minute candles: 30 provider calls, 26 s), which
  is why the read timeout is minutes while the connect timeout stays at five seconds.
- `hub.py` — fan-out to subscribers, and the hold that makes a snapshot airtight.
- `app.py`, `contract.py`, `errors.py` — the published surface, the shapes it answers with,
  and refusals that name themselves instead of leaking a database error.
- `migrations/` — the schema, as the statements a deployment actually runs. Handwritten SQL:
  there is no ORM model layer to diff against, so `--autogenerate` yields nothing useful.

Three tables, each answering a question the others cannot. **`candles`** is keyed on
`(symbol, resolution, period_start)`, so a period written twice is overwritten rather than
doubled, and stores `price_side` and `source` beside the data instead of assuming them.
**`tracked_pairs`** is the durable answer to what is collected — untracking flips a state and
stamps `untracked_at` rather than deleting, because an archive that drops data when its
configuration changes is not an archive. **`coverage_ranges`** is the stretch of time the
archive has actually verified.

## Run

```bash
cp .env.example .env       # gateway URLs and a PostgreSQL connection
docker compose -f ../../compose.yaml up -d db
uv run alembic upgrade head
uv run uvicorn market_data.app:app --reload --port 8020
```

Needs `capital-gateway` running on `http://localhost:8010` and a PostgreSQL to write to. The
repository's `compose.yaml` provides one on **port 55432** — not 5432, because a developer
machine very often already runs PostgreSQL of its own, and migrating somebody else's database
by accident is worse than failing to connect. `.env.example` already points there.
`../../scripts/dev.sh` (or `dev.ps1`) does all of the above plus the gateway and the terminal,
in the order they need each other. Migrations step with `uv run alembic downgrade -1`.

| Variable | Default | What it is |
| --- | --- | --- |
| `GATEWAY_BASE_URL` | `http://localhost:8010` | the gateway's HTTP contract |
| `GATEWAY_STREAM_URL` | `ws://localhost:8010/ws/stream` | the gateway's live feed |
| `DATABASE_URL` | — | required; the archive's own storage |
| `BACKFILL_CONCURRENCY` | `1` | deep fills allowed to run at once |
| `DEFAULT_BACKFILL_BARS` | `5000` | how far back a newly tracked pair reaches |
| `MAX_TRACKED_PAIRS` | `20` | ceiling on archived (symbol, resolution) pairs |

The last three are budgets rather than preferences, and each default is the cautious end. One
deep fill is dozens of back-to-back requests through the gateway's shared rate gate, so two at
once are enough to starve the chart an operator is looking at right now. The ceiling is real —
the gateway holds one provider connection per `(symbol, resolution)` and the provider limits
how many a session may hold — and the number is a budget to raise on evidence, not one to
discover by having the feed die.

## Test

```bash
uv run pytest                      # unit tests only; anything needing a database is skipped
uv run pytest -m db                # integration tests, needs a running Docker daemon
uv run pytest -m live --run-live   # reads through a real gateway on :8010
uv run ruff check .
```

Tests marked `db` run against a throwaway PostgreSQL container, started for the session and
gone afterwards — a container rather than a shared development database, because the schema
is part of what is under test: a table left over from an earlier run is indistinguishable from
a migration that works. Without Docker they skip with a reason rather than failing with a
connection error, and the daemon check carries a two-second timeout, so a machine without
Docker does not pay a minute of silence to reach the same skip.

## Contract

HTTP, described by OpenAPI at `/docs`.

| Method | Path | Returns |
|--------|------|---------|
| GET | `/health` | whether the database answers, and what is being collected |
| GET | `/candles/{symbol}?resolution=&from=&to=` | the series, **plus what was never collected** |
| GET | `/coverage/{symbol}?resolution=` | verified ranges and the end of provider history |
| GET | `/pairs` | what is collected, with how collection is going |
| POST | `/pairs` | start collecting a pair |
| DELETE | `/pairs/{symbol}?resolution=` | stop collecting it; the candles stay |

**A range read says what it is not saying.** `uncovered` carries the stretches of the
requested window the archive never verified. That is not the same as periods with no candle:
a shut market has no candle either, and only one of the two is missing data.

**Every answer names the price side.** The archive holds bid, matching the gateway. A series
quietly compared against an ask-side one is off by a spread that reads as a real move.

**Refusals name themselves and carry nothing raw.** A ceiling reached is 409 with the count
and the setting to raise; a symbol the gateway will not serve is 422; a gateway that is down
is 504 rather than 500, because the archive is fine and retrying it as though it were at fault
is the wrong response.

### WebSocket — `/ws/candles?symbol=US100&resolution=MINUTE`

Not in the OpenAPI schema: OpenAPI has no vocabulary for WebSocket payloads, so a path there
would describe a contract it cannot state. A test keeps the path out of the schema.

```jsonc
// first, exactly once
{"kind":"snapshot","symbol":"US100","resolution":"MINUTE",
 "candles":[{"symbol":"US100","period_start":"2026-08-07T12:00:00Z","open":1.0,"high":1.2,
             "low":0.9,"close":1.1,"volume":10.0,"price_side":"bid","source":"history",
             "forming":false}],
 "forming":{"...":"the period currently being built, or null"}}

// then, as they happen
{"kind":"candle","symbol":"US100","resolution":"MINUTE","candle":{"...":"...","forming":true}}
```

The subscription is the query string and the module reads nothing back, so there is no client
protocol to get wrong. **The first message is always a snapshot; every message after it is a
change.** One message kind covers both settled and forming, because a consumer upserts by
`period_start` and two kinds would only make it reconcile them itself.

**There is no gap to close after connecting, and no duplicate to filter.** The snapshot is read
while the room is held still, the subscriber attaches before it is released, and the ingest
write happens inside that same hold. Without the last part there is a moment where a candle is
committed but not yet broadcast, and a subscriber attaching then gets it twice. That is why the
terminal no longer needs its "on resume, close the gap" rule.

Subscribing to a pair nobody chose to collect is refused **before** the handshake, and does not
start collecting it either — that is the decision the ceiling exists to keep deliberate.

## The rules, and what was measured

**A forming candle is never stored.** It changes with every quote and understates its own range
until the period closes. Offering one to `store.write_candles` raises rather than being dropped
quietly, and one forming candle rejects its whole batch — a half-applied batch leaves the caller
unable to learn which half landed.

**A history value outranks a streamed one.** The same period can arrive both ways and they are
not equally trustworthy: a stream disconnected for part of the period reports a range too narrow
and a volume it never saw, while a history read watched the period whole. Every other
combination may overwrite, including history over history — a refetch is the provider correcting
itself.

**Coverage is what makes an absence an answer.** Inside a verified range an empty period is
`Absence.MARKET_CLOSED`; outside every one it is `Absence.NOT_COLLECTED`, and only that is worth
going back to the provider for. Ranges are stored merged, including ranges that merely touch,
under a transaction-scoped advisory lock — the second writer's rows do not exist yet for a row
lock to catch. `history_ended` marks the range reaching as far back as the provider goes, and is
what stops backfill walking further back every night into data that was never there.

**Knowing when *not* to ask is half of ingest.** One task per tracked pair: close the gap,
subscribe, store closed candles until the socket ends, wait, repeat — the gap-closing inside the
loop, because a dropped subscription is also a stretch nobody was listening for. At any moment the
newest closed candle is up to one period old, and treating that as a gap would send a request every
period forever for a candle nobody has yet. Reconnection backs off from a second to a minute and
resets only once a subscription produces something. Fills share one `asyncio.Semaphore` held by the
supervisor — a per-pair budget is no budget. A failed fill comes back as a `FillOutcome` carrying
its reason, one operator-readable line per outcome, rather than stopping the other pairs.

**Being on the list proves nothing about collection.** A subscription can die without a sound, and
the only symptom is a series that stops growing. `collection_state` reads the age of the newest
candle — within two periods is healthy, beyond that it depends on whether the market is open, which
the gateway answers and this module does not. Without that answer the state is `UNKNOWN` rather
than a guess: there is no session calendar here.

**Derived resolutions come from the minute series.** `MINUTE_5` … `HOUR_4` are computed, not
fetched: eight separate resolutions cost eight times the traffic for data the finest one already
implies. `DAY` and `WEEK` are not, and never will be — their boundary follows the venue's session
rather than the clock, the same conclusion the gateway's `forming.py` reached. Not a materialized
view, though the design first called for one: `REFRESH` recomputes the whole thing, `CONCURRENTLY`
included, so at a year of minute candles settling one bar would rebuild the archive.

**The four-hour boundary was measured, not assumed** — a provider anchoring on a venue's open would
return candles of the right length and shape, offset by hours, and every one would look correct on
a chart. Measured August 2026 on `BTCUSD` and `US100` — the two most unlike sessions on offer, so
that an anchor following a venue's open would have made them disagree: periods start at 00, 04, 08,
12, 16 and 20 UTC, and derived values match the provider's own to within a float's hair. The same
run showed **the provider pausing for a few minutes around 21:00 UTC every day**, for both
instruments: every interior four-hour period holds all 240 of its minutes except the one starting
at 20:00, which holds 233–235. So `complete` is legitimately false for one period in six, forever,
and is not a data-quality signal — coverage is what answers whether data is missing.

**Nothing here is a continuous market, `BTCUSD` included.** It is a CFD on bitcoin rather than
bitcoin: capital.com runs it 23/5 like everything else, so it is shut at the weekend and takes the
same daily break, and that break is what the 20:00 period is short by. Bitcoin trading somewhere
else at 3am on Sunday changes nothing about what this provider will hand back — which is why the
live tests want a trading day, and why a pair that has stopped moving is not evidence of anything.

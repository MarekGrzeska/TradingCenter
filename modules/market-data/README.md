# market-data

The candle archive. `capital-gateway` is a window onto the provider and keeps nothing; this
module keeps what flew past it, so a chart, a backtest or an agent can read a series that
exists tomorrow as well as today.

**Two surfaces, one archive.** The REST contract below is what the terminal reads. At
`/mcp` the same module serves eleven read-only MCP tools, reduced for a model rather than
proxied for a chart — see "The tool surface". They were a module of their own until
19 August 2026; what they are now is a route, reading the same functions the routers read.

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
- `indicators/` — `kernel.py` (the math, ~20 primitives, no FastAPI or asyncpg import in
  sight), `warmup.py` (how far back a recursive one needs reading before its answer can be
  trusted), `catalogue/` (every indicator this module offers, as data — id, params, output
  shape, how to draw it — not as a type per entry; `spec.py` holds the entry shape, one
  module per group holds the entries). See "Indicators" below.
- `reads.py` — the reads with two consumers: the routers and the tools. Anything a tool
  would otherwise re-derive — "collected beats computed", the three states of a forming
  candle — lives here once, because a second copy of a decision that has been wrong twice
  is how the two surfaces drift apart.
- `tools/` — the tool surface itself: the eleven tools, the reduction that keeps a reply
  small, and the sentences that say what the numbers do not (`uncertainty.py`).
- `mcp_app.py` — one FastMCP instance, mounted at `/mcp` by `app.py`.
- `caller_access.py` — which caller may reach which surface, as one record in front of the
  whole application. See "The tool surface".
- `hub.py` — fan-out to subscribers, and the hold that makes a snapshot airtight.
- `app.py` — assembly only: the lifespan, the error handling every route shares, and the
  routers mounted onto it. Nothing that decides anything.
- `routers/` — the routes, split by the area they serve rather than by verb: `meta`,
  `candles`, `pairs`, `jobs`, `stream`, `indicators`. That is how the specs are organised and
  how changes arrive — a change to jobs touches four routes that are all in one file and none
  of the others. `routers/deps.py` holds the two things a route reaches for, so a router never
  imports the module that mounts it.
- `tickets.py` — one-time tickets, which are how a browser opens the stream. See below.
- `contract.py`, `errors.py` — the shapes the module answers with, and refusals that name
  themselves instead of leaking a database error.
- `market_status.py` — whether an instrument's market is open, remembered for a minute. It
  is what lets the pair list tell a stalled pair from a shut market, and the minute is why
  reading that list does not cost a gateway request per closed pair forever.
- `migrations/` — the schema, as the statements a deployment actually runs. Handwritten SQL:
  there is no ORM model layer to diff against, so `--autogenerate` yields nothing useful.

Three tables, each answering a question the others cannot. **`candles`** is keyed on
`(symbol, resolution, period_start)`, so a period written twice is overwritten rather than
doubled, and stores `price_side` and `source` beside the data instead of assuming them.
**`tracked_pairs`** is the durable answer to what is collected — untracking flips a state and
stamps `untracked_at` rather than deleting, because an archive that drops data when its
configuration changes is not an archive. **`coverage_ranges`** is the stretch of time the
archive has actually verified.

## Packages it takes

`tc-runtime`, partially: `migrate`, `schema_version` and the advisory-lock helper. This
module keeps its own `db.py` — it has `connect()`, which nothing else does, and its own
pool defaults (`packages/tc-runtime/README.md`).

`tc-mcp-kit`, for one thing: `slim_tool_schemas`, which takes the scaffolding pydantic
writes for its own sake out of every published tool schema — 22,6% of what a client reads
before each turn, and not one field, type or `required` entry with it. The caller-identity
middleware in that package is *not* taken: it answers "is anybody there", and this module
has two surfaces and needs the narrower answer `caller_access.py` gives.

## Run

```bash
cp .env.example .env       # gateway URLs, this module's caller key, the database identity
uv run alembic upgrade head
uv run uvicorn market_data.app:app --reload --port 8020
```

Needs `capital-gateway` running on `http://localhost:8010` and a PostgreSQL to write to — the
container in `../../compose.yaml` (`docker compose up -d db` from the repo root, or let the
dev script do it). `.env.example` matches that container exactly, so a fresh checkout copies
it and edits nothing about the database. `../../scripts/dev.sh` (or `dev.ps1`) does all of
the above plus the gateway and the terminal, in the order they need each other. Migrations
step with `uv run alembic downgrade -1`.

`alembic upgrade head` above is the local convenience, not the mechanism: **the module
migrates its own database at startup** (`migrate.py`, called from `app.py`'s lifespan),
before a request is served and before a single candle is written. Production has no step
of its own at all — a merge to `main` leaves it serving.

Two things hold that up. Migrations run under a Postgres advisory lock (`db.py`), so two
instances starting together produce one migration and one waiter rather than the race the
`Dockerfile` used to refuse on. The wait is twenty-five minutes here against the agent's
five, because the candle table is the largest thing in this system and an index rebuilt
over it outlasts several ordinary starts. And they run as the module's **own** identity,
not the server administrator's, so every table they create belongs to the role that will
read it — the reason there is no `GRANT` step here any more. That was the half with no
check on it: `agent` lost `prompt_revisions` to exactly that on 15 August, reading as
`permission denied` rather than as a missing table.

`schema_version.py` still runs, immediately after. It now catches the narrower pair the
migration cannot fix: an upgrade that reported success without arriving, and an image
older than the schema it found — the second being a rollback that moved the code back and
left the database where it was. The first version of that check was written after
10 August, when a deploy landed new code on the previous schema and four routes answered
`500` for thirty-five minutes while the deploy sat green.

Leaving `DATABASE_USER` unset is what makes this local mode, and it cuts the module down to
loopback: without an identity it refuses any remote host, production included
(openspec: `market-data-database-connection`). The remote shape — Entra identity, TLS, no
credential in the URL — is production's, selected by `DATABASE_USER` in
`infra/app-service.tf`.

| Variable | Default | What it is |
| --- | --- | --- |
| `GATEWAY_BASE_URL` | `http://localhost:8010` | the gateway's HTTP contract |
| `GATEWAY_STREAM_URL` | `ws://localhost:8010/ws/stream` | the gateway's live feed |
| `GATEWAY_API_KEY` | — | required; must match the gateway's own key — it answers 401 without it |
| `DATABASE_URL` | — | required; the archive's own storage — locally the compose.yaml container, password and all |
| `DATABASE_USER` | unset | selects the connection mode: unset = local, loopback only; set = the Postgres role for identity auth, remote/production's shape (TLS mandatory, no credential in the URL) |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID` | unset | identity mode only, together or not at all — and unset even in Azure, where the App Service's own managed identity needs no configuration |
| `BACKFILL_CONCURRENCY` | `1` | deep fills allowed to run at once |
| `DEFAULT_BACKFILL_BARS` | `5000` | how far back a newly tracked pair reaches |
| `MAX_TRACKED_PAIRS` | `160` | ceiling on archived (symbol, resolution) pairs — 20 instruments across all eight resolutions |

The last three are budgets rather than preferences, and each default is the cautious end. One
deep fill is dozens of back-to-back requests through the gateway's shared rate gate, so two at
once are enough to starve the chart an operator is looking at right now. The ceiling is real —
the gateway holds one provider connection per `(symbol, resolution)` and the provider limits
how many a session may hold — and the number is a budget to raise on evidence, not one to
discover by having the feed die. Read what it counts before setting it: an operator watching
one instrument on every time frame spends eight of the budget, not one.

## Test

```bash
uv run pytest                      # unit tests only; anything needing a database is skipped
uv run pytest -m db                # integration tests, needs a running Docker daemon
uv run pytest -m live --run-live   # reads through a real gateway on :8010
uv run ruff check .
uv run pyright                     # types, over `market_data/` and `migrations/`
```

Tests marked `db` run against a throwaway PostgreSQL container, started for the session and
gone afterwards — a container rather than a shared development database, because the schema
is part of what is under test: a table left over from an earlier run is indistinguishable from
a migration that works. Without Docker they skip with a reason rather than failing with a
connection error, and the daemon check carries a two-second timeout, so a machine without
Docker does not pay a minute of silence to reach the same skip.

## How a browser opens the stream

Every route here is meant to be reached with a token in the `Authorization` header, and
in Azure something in front of the module (Easy Auth) checks it. `/ws/candles` is the one
that cannot be: **the browser's WebSocket API takes no headers**, so there is nowhere to
put the token, and putting it in the URL instead would write a credential valid for the
better part of an hour into every access log.

So the path is exempted from Easy Auth (`infra/app-service.tf`, `excluded_paths`) and
guarded here instead. A consumer asks `POST /stream-tickets` — an ordinary request, with
an ordinary header, checked in the ordinary way — and gets a **one-time ticket**, good for
one handshake and for thirty seconds. It is spent the moment it is presented; a second
attempt with the same ticket is refused, and so is one that sat unused too long. A ticket
that leaks out of a log has already been used.

Every attempt needs its own ticket, including every retry after a dropped connection.

Two things to know before changing any of it:

- **The ticket store is a dict in this process.** That works because the module runs as a
  single always-on instance (`worker_count = 1`). A second worker or a second instance
  would refuse tickets its neighbour issued, and the symptom — a stream that fails to
  connect now and then — points nowhere near the cause. Moving the store into Postgres is
  the answer if that day comes; `tickets.py` is the only file involved.
- **CORS is configured on App Service, not here.** The preflight the browser sends before
  a cross-origin request carries no credential at all, so Easy Auth would answer it with a
  401 before this application saw it — CORS has to be answered by something standing in
  front. Adding `CORSMiddleware` here would double the `Access-Control-Allow-Origin`
  header, and a browser rejects a response carrying two.

A consumer that is not a browser needs none of this: it sets a header on its own WebSocket
client and Easy Auth handles it, exactly as on every other route.

## The tool surface

`/mcp`, streamable HTTP, eleven tools and three resources. What a model gets is not the
REST contract in another spelling: a chart wants every candle, a model wants a summary, so
a series above the ceiling comes back bucketed and named as bucketed, a series far above it
is refused with what to ask instead, and every empty answer says which kind of empty it is.
`uv run pytest tests/test_tools_*.py` is that half of the module.

Every tool is annotated read-only and none reaches a route that writes. That used to be
true by construction — the tools were a separate module with no address for anything but
`GET` — and it is now true by record:

- `caller_access.py` holds route against caller. `agent` and `teams` reach `/mcp` and
  nothing else; the terminal reaches REST and never `/mcp`; `/ping` and `/ws/candles` are
  open with no identity, each for a reason written beside it.
- **A path the record does not name is refused, not passed**, so a REST route added next
  month is not reachable by a tool caller on the day it is written.
- The lists are `TOOL_CALLER_APPLICATION_IDS` and `REST_CALLER_APPLICATION_IDS`, read only
  where `REQUIRE_AUTHENTICATED_PRINCIPAL` is on. Locally they are empty and every surface
  answers: nothing stands in front, so there is no identity to match.
- **The identity is the calling application, taken from the token's own `azp`/`appid`
  claim** — not from `X-MS-CLIENT-PRINCIPAL-ID`, which for the terminal's delegated token
  carries the signed-in person. Measured in production on 19 August 2026, the hard way:
  deciding on that header refused every REST request until the image was rolled back.

The platform's own gate is still there and still necessary — it is the door. This record is
which room, and Easy Auth cannot express it: it authorizes an application, and an
application admitted for eleven read-only tools would otherwise also be admitted to
`POST /pairs` and `DELETE /pairs/{symbol}`.

## Contract

HTTP, described by OpenAPI at `/docs`.

The same document prints without starting anything — no database, no gateway, no settings,
because FastAPI builds it from the models in `contract.py`:

```sh
uv run python -m market_data.openapi > schema.json
```

The terminal generates its wire types from that, instead of keeping a hand-written copy that
nothing checks (`npm run contract:generate`, in `modules/terminal`). Change a model here and the
terminal stops compiling at the line that reads the field — which is the point. Regenerating
deliberately needs no running stack: a check that needs one is a check nobody runs.

| Method | Path | Returns |
|--------|------|---------|
| GET | `/health` | whether the database answers, and what is being collected |
| GET | `/ping` | whether the process is up — nothing else, no authentication required |
| GET | `/candles/{symbol}?resolution=&from=&to=` | the series, **plus what was never collected** |
| GET | `/coverage/{symbol}?resolution=` | verified ranges and the end of provider history |
| GET | `/pairs` | what is collected, how collection is going, and where each pair's history starts |
| POST | `/pairs` | start collecting one or more pairs, from a given moment |
| DELETE | `/pairs/{symbol}?resolution=` | stop collecting it **and delete its data**, irreversibly |
| GET | `/deletions?symbol=&resolution=` | recorded deletions, newest first |
| POST | `/jobs/estimate` | price a collection job without creating it |
| GET | `/jobs?symbol=&resolution=` | jobs, one row per pair they touched |
| GET | `/jobs/{id}` | one job, whole — every pair and chunk it covers |
| POST | `/jobs/{id}/retry` | retry a job's failed or interrupted chunks |
| GET | `/instruments?max_nodes=&asset_class=` | the catalogue, proxied from the gateway unread |
| GET | `/instruments/search?q=` | a search, proxied from the gateway unread |
| GET | `/asset-classes` | the classes the gateway describes instruments with |
| GET | `/indicators` | every indicator this module can compute, and how to draw it |
| POST | `/indicators/{symbol}` | one or more of them, computed over a range, on one shared time axis |

**`/ping` proves the process is up, not that it is healthy.** It is the one route Easy Auth
excludes from authentication alongside `/ws/candles` (`infra/app-service.tf`), because an
external availability probe needs to reach the container itself — Easy Auth answers 401 for
everything else whether the container is alive or dead, so a probe stopped there could never
tell the two apart. It reads nothing (no database, no gateway, no tracked-pair state) and
returns a fixed body for exactly that reason: `/health` above already answers whether the
database is reachable, and a route meant to catch a dead container has to answer while every
one of its dependencies is down.

**The last three are a proxy, not a second catalogue.** `capital-gateway` is not public — the
terminal cannot reach it directly — so these forward the gateway's own routes and its own JSON,
unmodified, using the caller key this module already holds for its other calls to the gateway.
A gateway refusal (its 401 for a missing or wrong key, or anything else) comes back as `502`,
never as a quiet empty list.

**A range read says what it is not saying.** `uncovered` carries the stretches of the
requested window the archive never verified. That is not the same as periods with no candle:
a shut market has no candle either, and only one of the two is missing data.

**Every answer names the price side.** The archive holds bid, matching the gateway. A series
quietly compared against an ask-side one is off by a spread that reads as a real move.

**Refusals name themselves and carry nothing raw.** A ceiling reached is 409 with the count
and the setting to raise; a symbol the gateway will not serve is 422; a gateway that is down
is 504 rather than 500, because the archive is fine and retrying it as though it were at fault
is the wrong response.

### Deleting a pair

`DELETE /pairs/{symbol}` used to only flip a pair to untracked; the candles stayed, on the
principle that an archive should not discard data as a side effect of a configuration change.
That principle still holds — nothing here deletes on its own, on a restart, or because a pair
was merely untracked — but it left no way to ask for data to actually go, and a pair re-added
with a shorter range kept its old, wider one: the leftover coverage told planning the range was
already fetched, so the next job pulled nothing.

The endpoint now deletes: it stops collection, releases the provider connection, and removes
every candle and coverage range the pair holds, in one transaction — a pair left with candles
gone but coverage intact would look, to planning, exactly like a pair already fully collected.
Deleting a symbol's `MINUTE` series also removes the rollups computed from it (`MINUTE_5` through
`HOUR_4`), since those are a projection of the deleted series rather than data of their own.
Deleting one resolution never touches another archived resolution of the same symbol.

What survives deletion: the pair's row in `tracked_pairs` (kept for the foreign key every chunk
and every deletion record relies on to name a pair tracking actually decided on), and every
collection job that ever touched the pair — a job is a record of what happened, and deleting the
data does not undo that it happened. What is added: a row in `pair_deletions`, readable through
`GET /deletions`, naming the pair, when, how many candles were removed, and the range they
covered (both null when there was nothing to remove) — without it, a pair's data reaching
further back one day and less far the next would be a fact with no explanation.

Deletion is not atomic with stopping the live subscription. It runs as two steps around one
in-process operation: close the decision (untrack the pair, skip its still-pending chunks) inside
one transaction, sync ingest — which is what actually closes the subscription and is not a
database write — then remove the data inside a second transaction. A chunk already claimed when
deletion starts can still finish afterwards; `execute_chunk` checks whether its pair is still
tracked before writing, so a gateway answer that arrives after deletion is discarded rather than
resurrecting what the operator just removed.

### Collection jobs

`POST /pairs` still takes the original single-pair body (`symbol`, `resolution`) and it still
means the configured default depth — nothing that spoke to this endpoint before needs to
change. It also takes a `pairs` list plus a `collect_from` moment, adding several pairs as one
decision. Accepting at least one pair that needed history behind it creates a **job**: a
durable record, split into **chunks** — one pair, one time window, one gateway request each,
newest first. A chunk that fails is named and does not stop the others; a chunk that discovers
the end of the provider's own history settles as done and every chunk still queued behind it
for that pair is skipped in bulk, rather than each spending a request to rediscover the same
edge. `collect_from` earlier than the provider's own history is clipped, never refused — asking
for 1850 means "everything there is."

A job's status (`running`, `succeeded`, `partial`, `failed`, `interrupted`) is never stored; it
is derived from its chunks' states every time it is read, so a process that dies mid-job cannot
leave two disagreeing records of the same fact. Restarting flips every chunk left `pending` or
`running` to `interrupted` — no runner survives a restart, so a chunk still queued is exactly as
orphaned as one mid-request. `POST /jobs/{id}/retry` resets only `failed` and `interrupted`
chunks, as a new attempt of the same job; it is refused with 409 when there is nothing to retry.

A job also answers **when something last happened in it** — `last_activity_at`, the newest of
its chunks' starts and finishes, and the job's own creation while nothing has been claimed yet.
A chunk that started counts: a chunk working for forty minutes and a chunk stuck for forty
minutes report the same progress and the same candle count, and this is the only field that
separates them.

The worker loop survives its own failures. A chunk that blows up is settled as `failed` and the
worker moves on; a failure in *taking* work — the database underneath the claim — is logged and
retried after a wait that doubles from 5s to a 60s ceiling, because that failure used to end
collection for the whole module until somebody restarted it. Only shutdown ends the loop.

`POST /jobs/estimate` runs the same planning a job creation would — without writing anything —
so a caller can price a decision before making it. The estimate is honest about being one: it
counts calendar periods, not a session calendar, so it overstates a market that is shut part of
the time.

### WebSocket — `/ws/candles?symbol=US100&resolution=MINUTE`

No path in the OpenAPI schema: OpenAPI has no vocabulary for a WebSocket, so an entry under
`paths` would describe a contract it cannot state. A test keeps the path out.

The **messages** are in the schema, as the `Snapshot` and `CandleChange` components. They are
ordinary Pydantic models, they are the most-read part of this contract — a chart sees every
candle through them — and the terminal generates its types from them rather than copying them
by hand. `openapi.py` hangs them on the document FastAPI builds from the routes, and the app
publishes that same augmented document, so `/openapi.json` and the dump below are the same
bytes.

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

### Indicators

One implementation of the math, on the server, for every future consumer — the terminal, a
backtest, the strategy module someday — rather than each reimplementing it and quietly
disagreeing. `GET /indicators` is the whole catalogue: id, parameters with their bounds, and
how to draw the answer. A consumer never needs to know an indicator by name beforehand — it reads
the catalogue and offers whatever it already knows how to draw. `POST /indicators/{symbol}`
computes one or more of them over a range, reading further back than `from` on its own by
however much warmup each one needs, and says in `settled` whether the archive actually held
enough history for the answer to be trusted yet — an unsettled value is still returned, never
withheld, because a caller silently missing a value is worse than one that knows to distrust it.

**A refusal is per indicator when it is the archive's, per request when it is the caller's.**
An entry reading a series other than the one being drawn — the session ranges, the opening
range, the time profile, the previous-period levels — cannot be computed for a pair nobody
collects that series for. That is not a bad request: it is a property of what someone chose to
collect, it changes without the request changing, and it differs entry by entry. So it comes
back as `error` on that one result, the rest of the request answers normally, and the status is
`200`. A caller's own mistake stays a `422` carrying `Problem` — an unknown indicator id, a
parameter outside the catalogue's range, a range ending before it starts, a request over the
ceiling — because a quiet partial answer to a typo is one nobody notices. A result carrying
`error` carries no shape: an empty `zones` list means the range held none, which is a different
claim, and the model refuses to be built with both.

Every answer takes one of four shapes, declared per entry and unrelated to which trading school
named the indicator: **lines** (a moving average, an oscillator), **markers** (a swing point),
**zones** (a gap, a session window — open on one end while unresolved, closed once it is),
**levels** (a pivot, a cluster of equal highs, a previous day's OHLC, a time-profile bucket).
`algorithm_version` bumps whenever a formula changes and never when an entry is only added —
`test_indicators_catalogue.py`'s golden file turns a silent formula change into a diff in the
same commit that made it.

**Determinism is a product, not an accident.** The kernel is its own implementation, on `numpy`
— not TA-Lib in the runtime, not `pandas-ta` — because every third-party library seeds its
recursive filters (EMA, RMA, and everything built on them) its own way, and that seed cannot be
overridden per call. Instead, warmup here is a decay threshold: read enough bars that the
seed's influence falls below `1e-9`, and the value no longer depends on where a caller happened
to start reading — the property `test_indicators_catalogue.py`'s `TestStartIndependence` checks
for every decaying entry at once. TA-Lib is still in the box, as a `dev` dependency compared
against with an explicit tolerance and a written list of known differences — a seeding
difference is not a bug on either side.

**What this module does not compute**, on purpose, not yet by omission:

- **No signal, no boolean.** An indicator measures; it never decides. Every threshold a formula
  needs (`skip_session_gaps`, a value-area percentage, a pivot type) is a parameter the caller
  chose, echoed back in the response — never a constant this module picked for them. `range_gap`
  carries "Fair Value Gap" as an alias, never as its identifier, so one school's vocabulary
  never becomes the wire's.
- **No volume.** Nothing here reads it and nothing here will — this archive's `volume` field is
  not reliably populated for a CFD provider, and a family built on it would be quietly wrong for
  some instruments and not others. `time_profile` counts one-minute bars per price bucket
  instead of traded size for the same reason: a TPO reading, not a volume profile.
- **No state, no repaint.** Parabolic SAR, SuperTrend, ZigZag, and rebuilt series (Renko, Kagi)
  do not decay with warmup, they *change* with it — deepening the history read changes today's
  value, which is a different contract than everything else here promises. Left out deliberately,
  not forgotten.
- **No session calendar.** `market_status.py` knows whether an instrument's market is open now,
  not its calendar — so `session_range`/`opening_range` take a **fixed clock window** as
  parameters (`from_hour`/`to_hour`, or a UTC calendar day for the opening range) rather than
  looking up real trading hours, and Ichimoku/Alligator's future-shifted lines stay out entirely
  until a session calendar exists to place them against without drawing one into a weekend.
- **No second instrument.** Every indicator computes from one symbol's own series — a spread or a
  correlation would need a second one as an input or a parameter, and nothing here accepts that.

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

**The quiet fill respects `collect_from`, not just `default_backfill_bars`.** A pair with nothing
collected reaches back the configured default depth — but never further than its own
`collect_from`, the moment its history is meant to reach back to. A pair tracked without an
explicit one has `collect_from` computed from that same default depth, so nothing changes for it;
a pair tracked with an explicit, shallower moment used to get the deep default fill anyway, because
this fill and the job system that also backfills a wizard-added pair run independently and neither
knew about the other's bound. Fixed rather than coordinated: the two still do redundant work for
the same pair (harmless — `write_candles` dedupes by period, `record_coverage` merges ranges), but
neither reaches further back than asked, which is the part that was silently wrong.

**Being on the list proves nothing about collection.** A subscription can die without a sound, and
the only symptom is a series that stops growing. `collection_state` reads the age of the newest
candle — within two periods **plus three minutes** is healthy, beyond that it depends on whether
the market is open, which the gateway answers and this module does not. Without that answer the
state is `UNKNOWN` rather than a guess: there is no session calendar here, and inventing one is
wrong twice a day.

The same read carries the *oldest* candle of each pair, from the same aggregate. It is how far the
data actually reaches, which `collect_from` — how far it was asked to reach — does not answer while
a job is still running or the provider's history ends later. It rides on the list rather than being
asked for per pair, because the panel draws it on every row.

Those three minutes are measured, not padding. A closed minute candle took 52 to 169 seconds to
reach the archive on 2026-08-08, so a perfectly healthy pair sits 112–229 seconds behind against a
bare two-period threshold of 120 — and the state flipped between `COLLECTING` and `STALLED` between
one read and the next while nothing was wrong. An indicator that cries wolf is worse than none. The
grace is a fixed span rather than a third period, because delivery takes the same few seconds at
every resolution while a third period would be four more hours at `HOUR_4`.

**Only the late pairs cost a question, and only once a minute.** `/pairs` asks the gateway about a
market's status just for the pairs whose state turns on it — a fresh pair is `COLLECTING` whatever
the market is doing — and once per *symbol*, since the same instrument at two resolutions has one
session. On a healthy archive that is no requests at all. The answer is then remembered for a
minute, because a shut market is *permanently* late and without that every read of the list spends
a request per closed pair: 74 of them about one instrument over a quarter of an hour of a weekend,
measured before the cache existed, against 1 per minute after. A session changes twice a day, so a
minute of staleness costs nothing. A gateway that will not answer leaves the pair `UNKNOWN`, which
is what it already was.

**Each row carries its last fill.** A fill can run for tens of minutes and fail on one pair while
the rest carry on, so `last_fill` travels beside the pair rather than only into the log: what was
asked, what the archive took, what it cost upstream, and the failure named if there was one. It
lives in memory, so it is `null` for a pair whose fill has not run since the module started.

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

**The two run on different calendars, and it was worth measuring which.** Saturday 2026-08-08,
15:11 UTC: `BTCUSD` and `ETHUSD` reported `marketStatus: TRADEABLE` with a candle for the minute
then in progress, while `US100`, `GOLD` and `EURUSD` were `CLOSED` with nothing since Friday 21:00
UTC. Index, forex and commodity CFDs are 23/5 here; the crypto ones trade the weekend as well. Only
the daily break around 21:00 is common to both.

**A frozen series is not evidence of a closed market.** That same Saturday morning `BTCUSD` served
nothing between 04:59 and at least 06:04 UTC, quote included — an hour-plus provider outage, on an
instrument that `marketStatus` would have called `TRADEABLE` throughout. It was read at the time as
the weekend. Ask the gateway what the market's status is before concluding anything from a series
that stopped moving; that is the same distinction `collection_state` refuses to guess at.

## Telemetry

Two observable OpenTelemetry gauges (`telemetry.py`), both derived from the same per-pair age read
(`compute_ages`) every 60s and read by whichever exporter is configured — Application Insights in
production, nothing locally:

- `market_data.candle_age_seconds` — seconds since each tracked pair's newest candle, for pairs
  whose market isn't known to be closed. Human-readable, and not what `alert-candle-age-stale`
  alerts on: a healthy `DAY` pair sits near 86,400 seconds old and a healthy `WEEK` pair near
  604,800, so no single second threshold means the same thing across every tracked resolution.
- `market_data.candle_age_periods` — the same staleness in periods of each pair's own resolution,
  with `DELIVERY_GRACE` (`tracking.py`) subtracted first so a healthy pair reads near zero rather
  than near one. One threshold (3, in `infra/monitoring.tf`) then means the same thing whether the
  resolution is `MINUTE` or `WEEK` — one more period than the module's own `STALE_AFTER_PERIODS`,
  so the production alert stays a blunter safety net than the per-pair `STALLED` indicator, not a
  second copy of it.

A pair whose market the gateway reports closed appears in neither gauge.

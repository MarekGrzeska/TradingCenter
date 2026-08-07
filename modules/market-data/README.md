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

Everything else is still to be built; see `openspec/changes/add-market-data/tasks.md`.

## Run

```bash
cp .env.example .env       # gateway URLs and a PostgreSQL connection
uv run uvicorn market_data.app:app --reload --port 8020
```

Needs `capital-gateway` running on `http://localhost:8010` and a PostgreSQL to write to.

## Test

```bash
uv run pytest              # unit tests only; anything needing a database is skipped
uv run pytest -m db        # integration tests, needs a running Docker daemon
uv run ruff check .
```

Tests marked `db` run against a throwaway PostgreSQL container, started for the session and
gone afterwards. A container rather than a shared development database, because the schema
is part of what is under test: a table left over from an earlier run is indistinguishable
from a migration that works.

Without Docker those tests skip with a reason rather than failing with a connection error.
The check for a usable daemon carries a two-second timeout, so a machine without Docker
does not pay a minute of silence to reach the same skip.

## Configuration

| Variable | Default | What it is |
| --- | --- | --- |
| `GATEWAY_BASE_URL` | `http://localhost:8010` | the gateway's HTTP contract |
| `GATEWAY_STREAM_URL` | `ws://localhost:8010/ws/stream` | the gateway's live feed |
| `DATABASE_URL` | — | required; the archive's own storage |
| `BACKFILL_CONCURRENCY` | `1` | deep fills allowed to run at once |
| `DEFAULT_BACKFILL_BARS` | `5000` | how far back a newly tracked pair reaches |
| `MAX_TRACKED_PAIRS` | `20` | ceiling on archived (symbol, resolution) pairs |

Three of those are budgets rather than preferences, and the defaults are the cautious end
of each:

**`BACKFILL_CONCURRENCY`** is 1 because a deep fill is dozens of back-to-back requests
through the gateway's shared rate gate. Two of them together are enough to starve the chart
an operator is looking at right now.

**`MAX_TRACKED_PAIRS`** exists because the gateway holds one provider connection per
`(symbol, resolution)` and the provider limits how many a session may hold. The ceiling is
real; the number is a budget to raise on evidence, not a guess to discover by having the
feed die.

**`DATABASE_URL`** points at the first state this repository owns. That makes this the first
module that can lose something: rebuilding three years of minute candles for a hundred
instruments costs roughly 27 hours of provider calls, which is what turns backups from a
good habit into a requirement.

## Contract

Not published yet. It will carry candle reads by time range, a subscription whose first
message is a snapshot, a coverage report and management of the tracked pairs — see
`openspec/changes/add-market-data/specs/market-data-api/spec.md`.

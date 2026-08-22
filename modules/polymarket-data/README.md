# polymarket-data

The prediction-market archive. One door to Polymarket, one database, two surfaces in one
process: the REST contract the terminal reads, and eleven-ish tools at `/mcp` the
workbench reads.

A market's price for an outcome is a probability, and a probability over time is a series
of the same kind as a candle. This module keeps that series. It does not alert on it, does
not translate anything and does not judge whether an event matters — that is the
workbench's work, done on this module's data.

```bash
uv run alembic upgrade head
uv run uvicorn polymarket_data.app:app --reload --port 8070
uv run pytest        # unit; anything needing a database skips without Docker
uv run pytest -m db  # against a throwaway PostgreSQL (testcontainers)
uv run ruff check .
uv run pyright
```

Port **8070**. It was listed in `CLAUDE.md` among the ports belonging to nobody until this
module claimed it; a `.env` pointing at 8040 or 8050 still reads as a server that is off.

## What it collects, and what it refuses to

The unit of collection is an **event** — a question with one or more markets under it,
each market with one or more outcomes, each outcome with a price. A binary market is the
special case of two outcomes, not the shape everything else is trimmed to. The source
application this module replaces stored a sample only for markets whose outcomes were
exactly `Yes` and `No`, and multi-market events vanished without a line in a log.

Collection is a decision, never a side effect. Searching the provider's public database
through this module collects nothing; only tracking an event does. Ending the tracking
stops the sampling and **keeps every sample already collected** — deleting data is a
separate act, on the REST contract, and no tool can do it.

## Two things measured on the provider, which shaped the design

Both on 22 August 2026, and both are why this module does not simply copy its predecessor.

**One request per event, not two per market.** The metadata surface publishes
`outcomePrices`, and those values are the order book's midpoint to the digit, for every
outcome of every market of the event, in one response. The source application polls the
order book per token — 256 requests for a 128-market election event where one will do.
The equivalence is measured rather than promised, so every sample records which surface it
came from, and a test holds the two against each other.

**The provider forgets.** Of five recently resolved markets, four returned no price
history at all. Whatever is not collected before a market resolves does not exist
afterwards, which turns "we keep everything" from a preference into the only version that
works — and makes a gap in collection expensive in a way a candle archive's gap is not.

Two smaller ones, both traps: a price-history request is capped at **15 days** between
`startTs` and `endTs` — on the interval, not the point count, so a coarser resolution buys
nothing — and `endTs` is ignored, the response running to the present moment regardless.
Both edges are therefore checked when a sample is written, not merely asked for.

## Configuration

`.env.example` is the list. `DATABASE_USER` unset selects local mode and narrows the
module to loopback; set, it names the Postgres role and the credential becomes an Entra
token fetched per connection. `PROVIDER_USER_AGENT` is not decoration — a request without
one is refused at the provider's edge with a `403` that reads like a blocked address.

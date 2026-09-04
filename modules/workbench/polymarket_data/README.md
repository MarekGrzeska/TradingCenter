# polymarket-data

The prediction-market archive. One door to Polymarket, one database, two surfaces in one
process: the REST contract the terminal reads, and nine tools at `/mcp` the workbench
reads.

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
special case of two outcomes, not the shape everything else is trimmed to.

Collection is a decision, never a side effect. Searching the provider's public database
through this module collects nothing; only tracking an event does.

**An observation is collected, or it is gone.** There is no third state and no act that
produces one: removing an observation takes the event, its markets, its outcomes and every
sample collected for it, in one indivisible act on the REST contract. Stopping the sampling
and keeping the samples used to be a separate act; it produced a row that neither collected
nor left the list, and it is gone with the state it made.

## Eight tools, two of which write

Six read: search the provider's public database live, browse by tag, list what is tracked,
open one event, read an outcome's history, read its changes over a window. Two change the
**list of observations** — track an event and create a group — and both of them only add to
it.

That is a deliberate departure from `market-data`, whose specification says outright that
its tool set only reads, and it is named here rather than smuggled into the code. The rule
there is about the candle archive: a tool that wrote would be a tool that mutated it. Here
the writing tools change the same list an operator clicks in the terminal, and the hard
line is drawn somewhere else instead — **no tool deletes collected history**, and none of
the eight touches money, because this system trades nothing on Polymarket. Since the only
way off the observation list takes that history with it, a tool for it would be a tool that
deletes history; that is why `untrack_event` is not here any more.

A ceiling on how many events may be tracked exists for the same reason the writing tools
do: "track whatever looks interesting" is a sentence a model can mean literally. Refusing
is cheap; an invisible growth in load is not. The refusal sends the model to the operator
rather than telling it to free a place: freeing one now costs somebody's collected history,
and it used to cost it silently.

Which caller reaches which surface is the module's own record, route by route
(`polymarket_data/caller_access.py`), not the platform's: Easy Auth authorizes an
application, so a caller admitted for the tools would otherwise be past every REST route
including the one that deletes. A path the record does not name is refused, not passed.

## Where the shape came from

This module replaces an application the operator was already running outside this system —
`MarekGrzeska/MarketTools`, in C#, collecting prices to send a Telegram alert and deleting
history after seven days. It was read and measured on **22 August 2026** rather than
translated, and the measurement is why three of its central choices are reversed here: it
sampled per token where one request prices a whole event, it stored a sample only for
markets whose outcomes were exactly `Yes` and `No`, and it knew only the moments its worker
happened to be running, so a restart was a hole for good.

**A third of it is deliberately not here.** The alerting layer — Telegram, Truth Social, the
news aggregator, the model's judgement of whether an event matters — is 1 688 of its 4 715
lines, 36%, and none of it is missing: that work is the workbench's, done on this module's
data. What this module owes it is a series that is true.

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

## What made the screens slow, measured 31 August 2026

Both surfaces were reported loading slowly or not at all, and three things were behind it. Each is
worth knowing because each looks harmless in the code that has it.

**The newest price of every outcome cost a sort of the whole archive.** `DISTINCT ON (outcome_id)
... ORDER BY outcome_id, observed_at DESC` wants its two columns in opposite directions, which no
index this schema can hold provides, so every read sorted every sample ever collected. At 3,2M rows
it measured **3520 ms**; driven from `outcomes` with a `LATERAL`, **3,4 ms** — and flat in the
archive's depth rather than linear in it. The terminal asks for this every 30 s, `pocket` every 60.

**A tick held every connection in the pool.** `tick` gathers all tracked events, and each held its
connection through a round trip per market, per outcome and per collected range — 644 of them for a
measured 128-market event, once a minute. With the pool at ten and ten events tracked, a read waited
on `pool.acquire()`, which has no deadline. Three statements now cover an event whatever its size,
`SAMPLER_DB_CONCURRENCY` caps collection's share of the pool, and a read that still finds nothing
free is refused with a 503 after five seconds rather than left to the platform's 230 s idle cut.

**The database is one burstable core.** `B_Standard_B1ms`, shared by every module's database. The
two fixes above matter more here than they would on a larger server: sustained CPU exhausts the
burst credits, and what is then slow is every module at once, not this one.

## Configuration

`.env.example` is the list. `DATABASE_USER` unset selects local mode and narrows the
module to loopback; set, it names the Postgres role and the credential becomes an Entra
token fetched per connection. `PROVIDER_USER_AGENT` is not decoration: the provider's edge
selects on that header and refuses some HTTP clients' defaults — `Python-urllib` gets a
`403` where an absent header does not — so the module sends a value it chose rather than one
a dependency bump could change under it.

The REST contract is generated into the terminal rather than copied by hand
(`python -m polymarket_data.openapi`, read by `modules/terminal/scripts/contract.mjs`).
Nothing there imports those types yet — the subpage is a change of its own — but
`pnpm contract:check` fails the day this contract moves, so that subpage starts against
types that are true rather than against a file born stale.

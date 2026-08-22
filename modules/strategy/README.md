# strategy

The strategy platform. **A strategy is a catalogue entry, not a project** — it declares the
facts it needs, the parameters it may be tuned with, and one pure function from those to a
decision. Everything around that is written once and shared: fetching the facts, the gates
every strategy is subject to, recording each decision with its reason, the read-only tool
surface, and the backtest.

This is the move `market-data` already made one level down. Its indicator catalogue is a
contract for an entry plus one machinery around it, and adding an indicator touches exactly
one file. The same shape, one level up: adding a strategy must not change a file of this
module's runtime, and `tests/test_layering.py` refuses when it does.

## What it does not do

**It never touches an account.** No client for trading-mcp, none for the gateway; nothing
here places, amends or cancels an order, and no setting moves that line
(`openspec/specs/strategy-runtime`). A setup published here is a reading. Execution belongs
to the teams in the workbench, which have the limits for it — `TradeGuard`, order counts
per run and per day — and to the operator.

It also computes no indicators of its own. The facts come from market-data's REST contract,
the same catalogue the terminal and the agents read. A second implementation of the same
mathematics is two answers to one question that drift apart at the first correction.

## Running it

```bash
cp .env.example .env          # the defaults match compose.yaml
uv run alembic upgrade head   # the process does this itself; this is for a cold database
uv run uvicorn strategy.app:app --reload --port 8080
```

`uv run pytest` · `ruff check .` · `pyright`, like every other Python module here. Tests
marked `db` need Docker and start a throwaway PostgreSQL; without Docker they skip with a
reason. Nothing in the suite reaches market-data — the archive is an HTTP contract and the
tests double it at the transport.

**One step is the operator's, exactly once per database:** the app role must own the schema
it is about to alter — `scripts/grant-schema-ownership.sql`. A database without it gives a
module that will not start. Everything after that is the deployment's: the lifespan brings
its own database to this image's revision under an advisory lock (key 8080), before it
serves anything.

## The two surfaces

**REST**, at 8080, for the operator and the terminal: the catalogue, the parameter sets, the
watches, and every decision with the reason it carries.

**`/mcp`**, in the same process, read-only: what the workbench's triggers read. The one tool
that shapes the rest is `pending_setups` — a number a trigger can compare against a
threshold, so the deterministic core finding a candidate is what wakes a team. That is the
intended seam between this module and the agents: the core decides, the team reads the same
decision and argues with it.

Nothing on `/mcp` writes. Activating a strategy, adding a parameter set and running a
backtest are the operator's, over REST — and `tests/test_tools_surface.py` asserts that of
the announced list rather than trusting this paragraph.

## Where the pieces are

| | |
|---|---|
| `strategy/spec.py` | the contract of an entry: `Fact`, `Param`, `Decision`, `StrategySpec` |
| `strategy/catalogue/` | the entries themselves, one file each |
| `strategy/archive.py` | the market-data client — the only thing here that does I/O for facts |
| `strategy/runner/` | the loop: closed bars, shared gates, one decision per bar |
| `strategy/backtest/` | replay over history, calling the same `evaluate` the loop calls |
| `strategy/gates.py` | the rules every strategy is subject to, whichever one it is |
| `strategy/routers/`, `strategy/tools/` | the two surfaces |

## The backtest

```bash
uv run python -m strategy.backtest --symbol US100 --from 2025-01-01 --to 2026-01-01 \
    --spread 1.5 --keep
```

A command rather than a route: a run over years of bars is minutes of work, and a long run
should not be something a caller sets off by accident. `--keep` writes the report where
`GET /backtests` reads it. Nothing about it is in the unit suite — what *is* tested is
everything it calls.

Two tests are the reason a report can be believed, and they are not two tests of one thing.
`test_incremental_and_batch_agree` reads the whole range once and slices it, then reads a
window per bar, and demands the two agree bar for bar — a difference is the future having
leaked backwards. `test_a_longer_range_does_not_change_the_common_part` extends the range
and demands the earlier decisions are untouched. Either one alone passes over the defect the
other exists for.

**A report with no cost model is not a result.** The archive holds the bid side, so the
spread is invisible in the data; a strategy with a wide reward over risk looks robust to
costs right up until they are put in. Every report names its costs, its parameter version
and its range, and `compare` refuses to put two runs side by side unless all three match.

## Two rules worth knowing before changing anything

**`evaluate` is pure.** No I/O, no clock, nothing outside its arguments. Everything downstream
stands on it: the unit tests hand it facts by hand, a recorded decision replays to the same
answer, and the backtest calls it directly rather than reimplementing it.

**A rule that binds every strategy belongs to the runtime; a rule one strategy might not
want belongs to its entry.** The first is written once and tested once. The second is what a
catalogue is for.

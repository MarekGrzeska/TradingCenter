# strategy

The strategy platform. **A strategy is a catalogue entry, not a project** — it declares the
facts it needs, the parameters it may be tuned with, and one pure function from those to a
decision. Everything around that is written once and shared: fetching the facts, the gates
every strategy is subject to, recording each decision with its reason, the read-only tool
surface, and the backtest.

**A package of the workbench since `one-process-per-security-boundary`**, served whole under
`/strategy` of that process — its REST contract, its `/mcp`, its caller record — with its own
database and its own migration chain (`alembic-strategy.ini`, lock key 8080, the port it used to
have). Its tools reach the conversation and the teams as functions, so there is no
`STRATEGY_MCP_URL` anywhere, and `pending_setups` is a local source the teams' clock reads. What
is the platform's alone is read under `STRATEGY_` in the workbench's `.env`; the archive it reads
(`MARKET_DATA_URL` / `_SCOPE`) and the door to Telegram are the process's, unprefixed. The
backtest CLI (`python -m strategy.backtest`) still builds `Settings()` from the unprefixed
environment, so run it with `STRATEGY_`-less names or from a shell that exports them.

This is the move `market-data` already made one level down. Its indicator catalogue is a
contract for an entry plus one machinery around it, and adding an indicator touches exactly
one file. The same shape, one level up: adding a strategy must not change a file of this
module's runtime, and `tests/test_layering.py` refuses when it does.

**An entry comes from one of two places, and nothing downstream can tell which.** It is
either code in the deployed image — `strategy/catalogue/`, reviewed like any other code — or
a rule the operator wrote on a screen, stored as an immutable revision and evaluated by
`strategy/interpreter.py`. `strategy/resolver.py` is the only file that knows there are two;
above it the loop, the gates, the record, the surfaces and the backtest are handed a
`StrategySpec` and never learn where it came from.

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
| `strategy/rule.py` | the node vocabulary a written rule is spelled in, and every check decidable without the archive |
| `strategy/interpreter.py` | evaluating one of those trees — `evaluate` for every written rule at once |
| `strategy/rule_validation.py` | the other half of a rule's validation, the half only the archive can answer |
| `strategy/resolver.py` | the one place an id becomes a `StrategySpec`, from either source |
| `strategy/catalogue/` | the coded entries themselves, one file each |
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
and its range, and `compare` refuses to put two runs side by side unless all three match. The revision is
the deliberate exception — `--strategy my_rule@3 --strategy my_rule@4` is the comparison this
command exists for, so it is named in every report rather than refused.

## A rule the operator wrote

A written rule is a tree of typed nodes in JSON — `const`, `param`, `fact`, `bar`,
arithmetic, comparisons, three-valued logic, `crossed`, `previous`, `settled` — with no
loops, no variables, no user functions and nothing reaching outside the facts and parameters
it is handed. There is no text syntax and no parser: the configurator composes the tree, so
the class of syntax errors does not exist.

That closure is what stands in for the code review a written rule will never get, together
with three more things: the definition is refused at the moment it is saved (against the
archive's own catalogue, so a nonexistent indicator or a range wider than the archive
accepts never becomes a strategy that records nothing), the module still has no route to an
account, and a written rule is expected to beat `baseline_ma_cross` on the same data and the
same costs before anyone acts on it.

**A revision is immutable and a watch pins one.** Saving a newer revision changes nothing a
running watch computes; moving it is a second, deliberate call. A parameter set belongs to a
revision rather than to a strategy, because a value inside its range under one revision may
have no declaration at all under the next.

`baseline_ma_cross` stays code, and `catalogue/baseline_rule.py` is the same rule written in
the vocabulary. It is deliberately not a second catalogue entry — it is the measuring stick:
`tests/test_baseline_rule.py` runs both over the same readings and demands the same answers,
which is the only honest test that the vocabulary carries a real strategy and that the
interpreter computes what it appears to.

## Two rules worth knowing before changing anything

**`evaluate` is pure.** No I/O, no clock, nothing outside its arguments — and that holds for
the interpreter as well as for a hand-written entry, under the same layering test.
Everything downstream stands on it: the unit tests hand it facts by hand, a recorded decision
replays to the same answer, and the backtest calls it directly rather than reimplementing it.

**A rule that binds every strategy belongs to the runtime; a rule one strategy might not
want belongs to its entry.** The first is written once and tested once. The second is what a
catalogue is for.

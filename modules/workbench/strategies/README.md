# strategies

The strategy engine, under `/strategies`. **A strategy is a document**, not code: it is saved as a row, checked when it
is saved, and replayed over the candle archive by an engine written once. A new strategy — or a new indicator in the
archive's catalogue — needs no change here and no deploy. Research only: nothing in this package can reach an account.

Why it exists and what was weighed: `openspec/changes/a-strategy-is-a-document`, and the research behind it in
`docs/strategie-i-backtesty-research.html`. Stage 1 of three: the screen and an agent that writes documents from a
sentence come next, then walk-forward and the other validation.

**Optional**, like the alerts: mounted only when `STRATEGIES_DATABASE_URL` is set; unset is a working process.

## What it does not do

- **No road to an account.** No client, address or setting for `trading-mcp` or the gateway; no route places, changes or
  cancels an order, and nothing publishes a decision. `tests/strategies/test_api.py` reads that off the source.
- **No verdict.** A report is numbers. Whether a strategy is worth anything is the operator's call.
- **No indicator mathematics of its own.** Indicators come from `/market`'s catalogue, over its REST contract in this
  process (`archive.py`). The language's own functions — windows, events, time — are its semantics, not indicators.
- **No delete.** A strategy is archived, never removed, and every run stays: the count of what was tried is what
  overfitting is judged by, and a count that loses rows lies.

## A document

```json
{
  "schema": 1, "name": "US100 pullback", "symbol": "US100", "timeframe": "HOUR",
  "params": {"fast": {"default": 20, "min": 10, "max": 30, "step": 5}},
  "let": {"fast": "ema(p.fast)", "slow": "ema(50)", "trend": "ema(20) @ HOUR_4 > ema(50) @ HOUR_4"},
  "entries": [{"side": "long", "when": "trend and low <= fast and close > fast",
               "order": {"type": "stop", "price": "high + 0.1 * atr(14)", "expires_bars": 3}}],
  "exits": {"stop": "entry_price - 2 * at_entry(atr(14))", "target": "entry_price + 3 * at_entry(atr(14))",
            "trail": {"after_r": 1.5, "distance": "1.5 * atr(14)"}, "when": "crosses_below(close, slow)", "max_bars": 48},
  "sizing": {"mode": "risk_fraction", "value": 0.005},
  "limits": {"daily_stop_r": -2, "no_entry": "weekday == FRIDAY and hour >= 18"}
}
```

One instrument per strategy. A stop is required: it is what 1 R measures. An unknown field is refused, not dropped. Every
save of changed content is the next immutable revision; the same content again is not.

## The language

Formulas use **Python's expression grammar**, parsed by `ast` and never executed: only the node types `formula.py` lists
survive into this package's own tree, and the interpreter only ever walks that tree. Python's grammar rather than one of
our own because every model that will write documents already knows it, and because it already parses what the language
needs — `close[1]` is a subscript, `close @ HOUR_4` the matrix-multiplication operator, `7 <= hour < 20` a chained
comparison. A test refuses any `eval`/`exec`/`compile` in the package.

- **Every name is in one registry** (`vocabulary.py`): the validator checks against it and `GET /language` is printed from
  it, so the two cannot disagree. Catalogue entries with a line output join it at each check.
- **No future.** An offset is a non-negative constant or parameter; `x @ HOUR_4` and `x @ US500` read the last bar of
  that series *available* at the decision — never the one still forming. A chain of `@` is one context
  (`x @ US500 @ DAY` reads US500 at DAY, never the traded instrument at DAY).
- **The trade's state** (`entry_price`, `open_r`, `at_entry(x)` …) stands only in exits; closed-trade history anywhere but
  a `let`; neither inside an offset or a window.

## The engine

Decisions on the close of each bar of the strategy's timeframe; fills settled on the traded instrument's `MINUTE` series
from the next minute. **The traded instrument must have its `MINUTE` series collected** — the check refuses a document
whose instrument has none. The archive holds the bid, so the ask is bid + the run's spread for that UTC hour.

Formulas without trade state are computed on numpy for the whole axis at once; formulas with it are interpreted bar by
bar, reading the first phase's columns (design D4). A test demands both agree with a series cut at each bar.

A minute whose range covers two events in an unknown order (stop and target, or a stop entry and its stop) is settled
against the strategy and marked. Costs are required on every run: hourly spread profile, slippage on orders that take
the price, financing for every rollover crossed (weekends too). `ENGINE_VERSION` in `engine.py` is raised by any change
that moves a result; the golden strategies (`tests/strategies/golden/`) refuse a moved result under the same number —
re-record with `uv run python -m tests.strategies.golden.regenerate`.

## Runs

`POST /runs` checks the request (parameters in range, costs present, range under `STRATEGIES_MAX_MINUTE_BARS`) and queues
it. The queue (`queue.py`) re-checks the revision against the archive as it is now, reads the data in this process —
parsing off the event loop — and computes in **a spawned process per run**, which a time limit or a cancellation stops.
A run left `running` by a stopped process is marked "interrupted by a restart" at the next start. The worker sends the
strategy's result before the random-entry benchmark, so a benchmark that runs out of time costs only itself.

## The report

R first, money as nominal units × points (no contract size, no currency conversion — design D6). Win rate, expectancy,
total R, profit factor, drawdown in R and %, Sharpe and Sortino from daily returns ×√365, Calmar, longest losing streak,
bars held, exposure, the total without the best five, a split by year, costs by component, and two benchmarks: buy and
hold, and random entry repeated from the run's seed. Every report records what it was made from — revision and hash,
parameters, costs, range, engine version, seed, and a fingerprint of every series read.

## Settings

Read under `STRATEGIES_` by `workbench/config.py`; the list is `.env.example`. Lock key **8130**. Not `STRATEGY_*`, nor
the database `strategy`: those belonged to the platform removed in October, and `ensure-databases.sh` still retires that
name on every deploy (design D1).

`uv run pytest tests/strategies` · `-m db` for the store, the queue and the routes.

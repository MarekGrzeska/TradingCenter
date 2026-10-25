# strategies

The strategy engine, under `/strategies`. **A strategy is a document**, not code: it is saved as a row, checked when it
is saved, and replayed over the candle archive by an engine written once. A new strategy — or a new indicator in the
archive's catalogue — needs no change here and no deploy. Research only: nothing in this package can reach an account.

Why it exists and what was weighed: `openspec/changes/archive/2026-10-25-a-strategy-is-a-document` (the engine) and
`openspec/changes/archive/2026-10-25-a-strategy-from-a-description` (the screen and the agent),
`openspec/changes/costs-come-from-the-broker` (costs read off capital.com, runs without costs, the strategy's own
conversation), and the research behind them in
`docs/strategie-i-backtesty-research.html`. Walk-forward and the other validation are stage 3.

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

One instrument per strategy. A stop is what 1 R measures, and it is optional: a document without one closes by `when` or
`max_bars`, may not use anything measured in R (`risk_fraction`, `trail`, `daily_stop_r`, `open_r`, `last_trade_r`),
and reports in % of equity instead. An unknown field is refused, not dropped. Every save of changed content is the next
immutable revision; the same content again is not.

A trade held through New York's session, without a stop — the operator's strategy of 25 October 2026:

```json
{
  "schema": 1, "name": "US100 — pierwsza M5 sesji NY wobec EMA12", "symbol": "US100", "timeframe": "MINUTE_5",
  "entries": [{"side": "long", "when": "session_bar(NEW_YORK) == 1 and close > ema(12)"},
              {"side": "short", "when": "session_bar(NEW_YORK) == 1 and close < ema(12)"}],
  "exits": {"when": "minutes_to_session_close(NEW_YORK) <= 5"},
  "sizing": {"mode": "margin_fraction", "value": 0.05}
}
```

Sizing: `risk_fraction` of equity per 1 R, `fixed_units`, `margin_fraction` — the deposit as a fraction of equity, with the
instrument's margin read off the broker (`margins.py`) — and `notional_fraction`, the position's value.

## The language

Formulas use **Python's expression grammar**, parsed by `ast` and never executed: only the node types `formula.py` lists
survive into this package's own tree, and the interpreter only ever walks that tree. Python's grammar rather than one of
our own because every model that will write documents already knows it, and because it already parses what the language
needs — `close[1]` is a subscript, `close @ HOUR_4` the matrix-multiplication operator, `7 <= hour < 20` a chained
comparison. A test refuses any `eval`/`exec`/`compile` in the package.

- **Every name is in one registry** (`vocabulary.py`): the validator checks against it and `GET /language` is printed from
  it, so the two cannot disagree. Catalogue entries with a line output join it at each check.
- **Sessions follow their city.** `NEW_YORK`, `LONDON` and `TOKYO` (`vocabulary.py`, the chart's session ranges, held
  equal by `tests/test_session_hours_agree.py`) are read through `session_bar` and `minutes_to_session_close`, by the
  clock in the session's zone (`sessions.py`) — no exchange holidays or early closes yet. `hour` and the rest stay UTC.
- **No future.** An offset is a non-negative constant or parameter; `x @ HOUR_4` and `x @ US500` read the last bar of
  that series *available* at the decision — never the one still forming. A chain of `@` is one context
  (`x @ US500 @ DAY` reads US500 at DAY, never the traded instrument at DAY).
- **The trade's state** (`entry_price`, `open_r`, `at_entry(x)` …) stands only in exits; closed-trade history anywhere but
  a `let`; neither inside an offset or a window.

## The engine

Decisions on the close of each bar of the strategy's timeframe; fills settled from the next minute on the **execution
series** (`document.execution`). A document with nothing to find inside a bar — no stop, target or trail, only market
entries — is settled on its own timeframe: the next bar's open *is* the next minute's open, so the trades are the same,
and no minute is read at all (the archive's minutes reach back months, its M5 years). Any other document is settled on
`MINUTE`: the check refuses one whose instrument has no `MINUTE` collected, and a run fails before computing anything
when a decision bar in its range has no minute under it — naming the gaps and the first minute there is, instead of an
order waiting months for the next minute. The archive holds the bid, so the ask is bid + the run's spread for that UTC
hour.

Formulas without trade state are computed on numpy for the whole axis at once; formulas with it are interpreted bar by
bar, reading the first phase's columns (design D4). A test demands both agree with a series cut at each bar.

When the equity marked with the open position reaches zero, the position is closed there as a stop would be
(`out_of_capital`) and nothing opens again — a floor no account goes below, not the broker's earlier close-out. On a
five-minute execution series the floor sees no gap inside a bar: crossed mid-bar, it closes at the floor, where minutes
might have closed at a worse open beyond it.

A minute whose range covers two events in an unknown order (stop and target, or a stop entry and its stop) is settled
against the strategy and marked. Every run has a cost model: hourly spread profile, slippage on orders that take
the price, financing for every rollover crossed (weekends too). `ENGINE_VERSION` in `engine.py` is raised by any change
that moves a result; the golden strategies (`tests/strategies/golden/`) refuse a moved result under the same number —
re-record with `uv run python -m tests.strategies.golden.regenerate`.

## Runs

`POST /runs` checks the request (parameters in range, range under `STRATEGIES_MAX_EXECUTION_BARS` candles of the execution series) and queues it. The queue (`queue.py`) re-checks the revision against the archive as it is now, reads the data in this process —
parsing off the event loop — and computes in **a spawned process per run**, which a time limit or a cancellation stops.
A run left `running` by a stopped process is marked "interrupted by a restart" at the next start. The worker sends the
strategy's result before the random-entry benchmark, so a benchmark that runs out of time costs only itself.

## Costs

A run's costs come from one of three places, and the run records which in its `request` (`costs_source`): the
request's own `costs`; the instrument's **cost profile** when the request names none; or `without_costs`, a choice that
gives a model of zeros and is marked in the report and the list — typed zeros are an ordinary model. Asking for both is
a refusal.

The profile is **read off the broker** the first time a run needs one (`broker_costs.py`), through `/market` in this
process — the package still has no road to the gateway: the spread is ask − bid of the archive's search for the exact
symbol, the financing and the settlement hour come from the instrument's terms (`GET /instruments/{symbol}/terms`).
capital.com states `longRate`/`shortRate` as a percentage of the position's value per day, negative when the holder
pays; the profile stores `−rate / 100`, positive being a charge — checked against a charge on the demo account (design
D3). The broker's own numbers are kept in `broker` beside the converted ones. A value the broker leaves out, or a
charge other than daily, is a refusal naming it, and nothing is written.

The profile is kept until the operator changes it (`PUT /costs/{symbol}`, `source = operator`) or asks the broker again
(`POST /costs/{symbol}/from-broker`) — never refreshed by a run, so two runs a day apart cost the same and compare.

## The report

R first where there is a stop, % of the equity at entry on every trade, money as nominal units × points (no contract size, no currency conversion — design D6). Win rate, expectancy,
total R, profit factor, drawdown in R and %, Sharpe and Sortino from daily returns ×√365, Calmar, longest losing streak,
bars held, exposure, the total without the best five, the deepest open loss (MAE), a split by year, costs by component, and two benchmarks: buy and
hold, and random entry repeated from the run's seed. Every report records what it was made from — revision and hash,
parameters, costs, range, engine version, seed, and a fingerprint of every series read.

## The conversation's tools

Nine, in `tools/`, built into a FastMCP server the assembly hands **to the conversation alone** as functions — never to
the teams (a schedule would spend the queue and the trial count on runs nobody asked for), never to the alerts'
catalogue, and never mounted at `/mcp` (design D7). `strategy_language`, `list_strategies`, `read_strategy` and
`validate_strategy` read; `draft_strategy` puts a document into the operator's editor as unsaved text — no revision,
no trial, one draft per strategy and one for the new strategy (`drafts.py`), ended by any saved revision; `save_strategy`
writes a revision authored `agent`, and needs `based_on` — the revision the
change was made to — or a newer one is a refusal; `run_backtest` queues a run marked `requested_by = agent`, with the
**instrument's cost profile** and no costs of its own, refuses while another of the agent's runs waits, and waits up to
`WAIT_SECONDS` for the result — read off the broker when there is none — or `without_costs` when the operator asks for
that in so many words; `read_backtest` and `compare_runs`, which refuses runs of different range, costs or engine.
The screen asks the same of `GET /runs/compare?run_id=…&run_id=…`, under the same rule (`compare.py`): 422 names every
difference, 404 a run that does not exist.
No tool sets a cost profile. The surface has a character ceiling in
`tests/strategies/test_tools.py`.

## What the screen reads

- **The summary** (`summary.py`) is the document read back in Polish from the document alone — no model, so a strategy
  the agent misunderstood reads as what it is. Every registry name has a phrase (`phrase`, `NAME_PHRASES`), and a test
  refuses one without. In `POST /validate` and every revision read.
- **Changes** (`changes.py`) between two revisions, by the paths problems use; the history and `save_strategy` share it.
- **A save based on a stale revision** (`?based_on=`) is a 409 naming the latest, so the editor and the agent never
  silently undo each other.
- **A strategy's conversation** (`PUT /strategies/{id}/conversation`, `conversation_id` in every read) is the id of the
  agent session the terminal's chat beside the editor reopens. Not a revision and not a trial; the id is never read here.
- **The report** is `ReportOut` in the contract, with the daily `equity` curve the ratios were computed from (engine 2;
  a v1 report has none) and where its costs came from (`costs_source`, `costs_fetched_at`, `without_costs`, read off
  the run's `request`). A list of runs reads the `headline` column, never the report, and marks a run without costs.

## Settings

Read under `STRATEGIES_` by `workbench/config.py`; the list is `.env.example`. Lock key **8130**. Not `STRATEGY_*`, nor
the database `strategy`: those belonged to the platform removed in October, and `ensure-databases.sh` still retires that
name on every deploy (design D1).

`uv run pytest tests/strategies` · `-m db` for the store, the queue and the routes.

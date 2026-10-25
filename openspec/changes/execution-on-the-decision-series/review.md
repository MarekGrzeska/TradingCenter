## Verdict

Shipped: a document with nothing to find inside a bar (no stop, target or trail, market entries only) is settled on its
own timeframe and reads no minute; every other document stays on `MINUTE` and its run fails before computing when a
decision bar has no minute under it. The ceiling, the run form and the report speak of the execution series. Knowingly
open: task 4.2, re-running the operator's US100 M5 backtest from 1 January 2026 after the deploy.

Not an oversight: the golden recording moved only its `engine_version` (3 → 4). No recorded result changed, including
`session_without_a_stop`, which now executes on M5 — the expected outcome on synthetic data with every minute present.
The version is raised for the runs that change: those over ranges where minutes were missing, like run 2 in production.

## Verified

- `modules/workbench`: `uv run pytest -q` → 3313 passed, 11 skipped (before the last test additions);
  `uv run pytest -q tests/strategies tests/test_tool_names.py` → 248 passed; `uv run pytest tests/strategies -m db` →
  passed against a throwaway PostgreSQL; `ruff check .` clean; `pyright` 0 errors.
- `uv run python -m tests.strategies.golden.regenerate` → "recorded 6 golden strategies under engine version 4", diff of
  `golden.json` one line.
- `modules/terminal`: `vitest run` → 1006 passed; `tsc -b --noEmit` and `eslint .` clean; `node scripts/contract.mjs
  check` → every contract up to date. `modules/pocket` contract check up to date (it does not consume strategies).
- `scripts`: `uv run pytest -q tests` → 215 passed, 27 skipped.
- `openspec validate execution-on-the-decision-series --strict` → valid.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `strategies/config.py:48` | The comment above the renamed ceiling still spoke of `MINUTE` candles. | FIXED before commit |
| Low | `strategies/engine.py:2`, `strategies/reports.py:112` | Docstrings reflowed past the line width after the edit. | FIXED before commit |
| Note | `strategies/reading.py` `bars_without_minutes` | September 2026 has a 13–15 September stretch with M5 bars and no US100 minutes, so a strategy with a stop over that month now fails with the gap named instead of running. Intended (`strategies-backtest`, "Brak minut pod strategią z poziomami jest niepowodzeniem"); worth knowing before reading a refusal as a bug. | By design |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| Decyzja na zamkniętej świecy… / Zlecenie rynkowe z sygnału | `tests/strategies/test_engine.py::test_a_signal_on_the_close_fills_on_the_open_of_the_next_minute_with_the_spread` |
| … / Strategia bez poziomów nie czyta minut | `tests/strategies/test_engine.py::test_a_strategy_without_levels_needs_no_minutes_under_its_bars`; `tests/strategies/test_documents.py::test_a_strategy_without_levels_needs_no_minutes_of_its_instrument` |
| … / Ta sama strategia na obu seriach | `tests/strategies/test_engine.py::test_a_strategy_without_levels_trades_on_its_bars_as_it_would_on_minutes`; the unchanged golden recording |
| (the rule itself) which documents go to `MINUTE` | `tests/strategies/test_documents.py::test_only_a_level_inside_a_bar_settles_fills_on_minutes` |
| Uruchomienie jest zadaniem w tle z limitami / Restart w trakcie | `tests/strategies/test_runs.py::test_a_run_left_running_by_a_previous_process_is_marked_interrupted` |
| … / Za długi zakres | `tests/strategies/test_runs.py::test_a_range_past_the_ceiling_is_refused_with_both_numbers` |
| … / Długi zakres strategii bez poziomów | `tests/strategies/test_runs.py::test_the_ceiling_counts_candles_of_the_series_fills_are_settled_on` |
| Brak minut pod strategią z poziomami… / Strategia ze stopem przed początkiem minut | `tests/strategies/test_runs.py::test_a_decision_bar_with_no_minute_under_it_is_named_with_the_first_minute_there_is`; `::test_a_strategy_with_a_stop_over_hours_without_minutes_fails_before_computing` (db) |
| … / Pojedyncza brakująca minuta | `tests/strategies/test_runs.py::test_a_single_missing_minute_is_not_a_gap` |
| Raport mówi, z czego powstał / Seria wykonania w odczycie agenta | `tests/strategies/test_runs.py::test_a_queued_run_is_computed_in_a_worker_and_leaves_its_trades_and_provenance` (provenance `execution`); `read_backtest` passes the key through (`strategies/tools/running.py`), no test of its own |
| … / Dane zmieniły się…, Raport strategii z ułamkiem depozytu | unchanged; their existing tests |
| Odczyt rewizji podaje serię wykonania / Rewizja bez poziomów | `tests/strategies/test_api.py::test_validate_answers_what_saving_would_and_writes_nothing` |
| … / Rewizja ze stopem | `tests/strategies/test_api.py::test_revisions_are_listed_compared_and_a_stale_base_is_a_conflict` (db) |
| Uruchomienie z formularza… / Zakres ponad sufit, Długi zakres strategii na M5 | `modules/terminal/src/strategies/RunForm.test.tsx` — "counts candles of the %s series the strategy is settled on" (MINUTE, MINUTE_5) |
| … / Instrument bez profilu kosztów | `RunForm.test.tsx` — "fills an instrument without a profile from capital.com and runs with nothing typed" |

## Gaps

- `read_backtest` returning `execution` is proven only through the stored provenance it copies; no tool-level test reads
  it back. One line of key list, judged not worth a database test of its own.
- Task 4.2, the production re-run, waits for the deploy.

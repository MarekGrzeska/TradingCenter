## Verdict

Shipped: `DELETE /runs`, the conversation's `delete_backtests` and the Backtests tab's “Usuń” remove finished, failed and
cancelled runs with their report and trades, all or none, and the strategy's trial count survives through
`strategies.deleted_trials` (migration `0006`). Knowingly incomplete: the closing of an open report when its run is
deleted is one line of view state with no test of its own.

Not an oversight: no soft delete and no undo (design D1), and no code-level gate on the agent beyond its description,
the cap of 20 and the refusal of runs in progress (D4). One addition beyond the specs: the queue now treats a run whose
row is gone as unwanted, so a worker still computing a run that was cancelled and then deleted is stopped.

## Verified

- `modules/workbench`: `uv run pytest -q` → 3319 passed, 11 skipped; `uv run pytest tests/strategies` including the `db`
  tests → 253 passed against a throwaway PostgreSQL (the migration ran as part of the fixture); `ruff check .` clean;
  `pyright` 0 errors.
- `modules/terminal`: `vitest run` → 1015 passed; `tsc -b --noEmit` and `eslint .` clean; `node scripts/contract.mjs
  check` → every contract up to date.
- `openspec validate delete-old-backtests --strict` → valid.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Medium | `strategies/queue.py` `_still_wanted` | A run cancelled and then deleted while its worker still computed was invisible to the cancel poll (the status was `None`, not `cancelled`), so the process ran to its end or the time limit. | FIXED in this change; test `test_a_run_cancelled_and_deleted_while_its_worker_computes_is_still_stopped` |
| Note | `strategies/runs.py` `delete_runs` | A `cancelled` row is deletable while its worker has not yet been stopped. Harmless: `finish` returns when the row is not `running`, and the poll above stops the process. | By design |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| strategies-backtest: Usunięcie… / Usunięcie zakończonego uruchomienia | `tests/strategies/test_runs.py::test_deleting_finished_runs_removes_them_and_their_trades_but_not_the_trials` |
| … / Usunięcie nieudanego uruchomienia | the same test (the failed run leaves `trials` at 3) |
| … / Uruchomienie, które się liczy | `test_runs.py::test_a_run_still_queued_or_running_or_missing_stops_the_whole_deletion` |
| … / Jedno z kilku nie istnieje | the same test |
| … / Wyścig z końcem uruchomienia | `test_runs.py::test_a_run_that_finishes_while_it_is_being_deleted_is_counted` |
| strategies-api: Usuwanie… / Usunięcie dwóch uruchomień | `tests/strategies/test_api.py::test_delete_runs_removes_what_is_asked_and_refuses_the_rest_whole` |
| … / Uruchomienie w toku | the same test (409 naming the run and its state) |
| … / Oglądający | `tests/test_roles.py` (the package is closed to `viewer` as a whole); no delete-specific test |
| strategies-tools: Powierzchnia… / Odczyt usuniętego uruchomienia | `tests/strategies/test_tools.py::test_the_agent_deletes_runs_on_request_and_the_trials_stay_and_a_run_in_progress_stops_it` |
| strategies-tools: Agent usuwa… / Usunięcie na prośbę, Uruchomienie w toku, Za dużo naraz | the same test |
| terminal-strategies: Usuwanie… / Usunięcie zaznaczonych | `modules/terminal/src/strategies/BacktestsView.test.tsx` — “deletes the runs ticked after asking, and lists what is left” |
| … / Uruchomienie w toku | `BacktestsView.test.tsx` — “lets a run in progress be cancelled but not ticked for deletion” |
| … / Odmowa pakietu | `BacktestsView.test.tsx` — “keeps the question open and names the run the package would not delete” |
| … / Otwarty raport usuniętego uruchomienia | — (gap) |

## Gaps

- Closing the open report after its run is deleted (`BacktestsView.deleteMarked`) has no test: ReportPanel needs the chart
  and a run to open, and the line is `setPickedRun(null)`.
- The `viewer` scenario relies on the package-wide role test rather than a delete-specific one; the route is not special.

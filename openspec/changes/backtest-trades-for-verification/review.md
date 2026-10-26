## Verdict

Shipped: `read_backtest_trades` (pages of up to 100, UTC), `GET /runs/{run_id}/trades.csv` (every trade, streamed a page of
1,000 at a time, UTC and Warsaw times, empty fields for what a trade does not have) and “Pobierz transakcje (CSV)” in the
report. `read_backtest` is unchanged and still carries no trade. Knowingly out of scope: checking rules for the reader
(“every exit before the session closed”) — the data is there, the check is theirs (design Non-Goals).

Not an oversight: the tool's `trades` are dicts built from `TradeOut`, not a typed list, to keep the tool schema the
model reads every turn two thousand characters smaller; the surface ceiling still had to rise from 11,500 to 13,500
(12,454 measured), which is the price of one more tool with a description worth reading.

## Verified

- `modules/workbench`: `uv run pytest tests/strategies` → 258 passed (including the `db` tests); `ruff check .` clean;
  `pyright` 0 errors. The full `uv run pytest -q` → 3316 passed, 8 failed, all in `tests/teams/test_scheduler_clock.py`
  (the cron clock of the teams package, which this change does not touch); `tests/teams` rerun later → 408 passed. See
  Gaps.
- `modules/terminal`: `vitest run` → 1017 passed; `tsc -b --noEmit` and `eslint .` clean; `node scripts/contract.mjs
  check` → every contract up to date.
- `openspec validate backtest-trades-for-verification --strict` → valid.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `strategies/tools/running.py` `TradesPage` | A first draft typed `trades` as `list[TradeOut]` and put the surface at 13,577 characters; the schema was most of the difference. | FIXED before commit (dicts, 12,454) |
| Note | `strategies/routers/runs.py` `trades_as_csv` | The 404 is decided before the stream starts; a run deleted while its file is being sent ends the stream early with the pages read so far. A deleted run's trades are gone, so there is nothing to send. | By design |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| strategies-tools: Powierzchnia… / Odczyt raportu nie niesie transakcji | `tests/strategies/test_tools.py::test_the_agent_reads_a_runs_trades_a_page_at_a_time_and_read_backtest_carries_none` |
| … other scenarios | unchanged; their existing tests |
| strategies-tools: Agent czyta transakcje… / Pierwsza strona, Druga strona | the same test (154 trades: 100, then 54, `total` 154) |
| … / Limit ponad sufit | the same test (101 refused naming “1 to 100”) |
| … / Transakcja bez stopu | the same test (stop and R `None`) |
| strategies-api: Transakcje jako CSV / Pobranie transakcji | `tests/strategies/test_api.py::test_trades_csv_has_every_trade_across_pages_and_a_missing_run_is_a_404` (154 rows over pages of 50, `text/csv`, file name) |
| … / Dwie strefy czasu | `tests/strategies/test_trades_csv.py::test_a_trade_is_written_in_utc_and_in_warsaw_summer_and_winter` |
| … / Transakcja bez stopu | `test_trades_csv.py::test_what_a_trade_does_not_have_is_an_empty_field_not_a_zero` |
| … / Brak uruchomienia | `test_api.py::test_trades_csv_has_every_trade_across_pages_and_a_missing_run_is_a_404` |
| (BOM, one header line, empty run) | `test_trades_csv.py::test_the_file_starts_with_the_byte_order_mark_and_one_header_line`; the empty run in the API test |
| terminal-strategies: Pobranie… / Pobranie przy stronicowanej tabeli | `modules/terminal/src/strategies/RunForm.test.tsx` — “saves the whole run, whatever page of the table is open” |
| … / Nieudane pobranie | `RunForm.test.tsx` — “says why it could not, and leaves the table as it was” |

## Gaps

- The terminal test proves the request is for the whole run and the saved file is named after it; that the browser then
  writes the bytes is the platform's. The route's CSV is proven separately, so no test reads a real file end to end.
- The full workbench suite had 8 failures in `tests/teams/test_scheduler_clock.py` between about 01:00 and 03:30 CET on 26
  October 2026 (the first run, and a rerun of `tests/teams`, 9 failures); the file passed alone, and `tests/teams` passed
  in full (408) at about 04:00 CET. None is in a file this change touches. It reads as a wall-clock flake of that file,
  which its own docstring says it has had before; it is recorded here and not investigated.

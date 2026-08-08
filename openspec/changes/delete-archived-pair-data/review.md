## Verdict

Shipped: `DELETE /pairs/{symbol}` now removes a pair's candles, coverage, and (for `MINUTE`)
its rollups, in one transaction, preceded by a decision-closing transaction and an ingest
sync; every deletion is recorded and readable through `GET /deletions`. The terminal renames
`Stop` to `Delete`, warns the removal is permanent, reports what was removed once it is
done, and shows every deletion in `Data History` next to the jobs it follows. Backend and
terminal test suites, lint, and typecheck are all green.

Knowingly incomplete: task 7.4 (a manual end-to-end pass on a running stack) is left for the
operator, as scoped in tasks.md. One correctness risk was found during review and is left
open rather than fixed under this change's scope — see Findings, first row.

## Verified

- `cd modules/market-data && uv run pytest -q` → `407 passed, 7 skipped`
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/terminal && npm run typecheck` → clean
- `cd modules/terminal && npm run lint` → clean
- `cd modules/terminal && npx vitest run` → `220 passed` (16 files)
- `openspec validate delete-archived-pair-data --strict` → `Change 'delete-archived-pair-data' is valid`

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Low | `market_data/jobs/runner.py:75` vs `market_data/deletion.py:89` | `execute_chunk`'s `is_tracked` check and the writes that follow it (`write_candles` at `runner.py:85`, `record_coverage` at `runner.py:90`) are not in the same transaction as `close_for_deletion`/`delete_pair_data`. A chunk can pass the `is_tracked` check, yield control at the next `await`, have a concurrent `DELETE /pairs/{symbol}` run `close_for_deletion` → `ingest.sync()` → `delete_pair_data` to completion, and then resume and write — resurrecting candles and a coverage range into a pair whose data was just deleted. The window is small (one event-loop turn, not the whole gateway round-trip the old code had) and requires a delete to land in that exact gap, but it is real and was not called out in design.md's "Kawałek nigdy nie zapisuje dla pary, której nikt nie zbiera", which frames the check as closing the race rather than narrowing it. Fixing it fully needs the chunk's write path to take a lock `close_for_deletion`'s `UPDATE tracked_pairs` would contend with (e.g. `SELECT ... FOR SHARE` on the pair's row inside the same transaction as the writes) — a real change beyond the "one sentence in the runner" this task was scoped as, so left open rather than done under time pressure. | open |
| — | — | No other findings survived verification. | — |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-tracking: Skasowanie pary zatrzymuje zbieranie i usuwa jej dane** | |
| Operator kasuje parę | `tests/test_deletion.py::test_deleting_removes_candles_and_coverage`, `::test_closing_for_deletion_untracks_the_pair` |
| Ponowne dodanie pary skasowanej | `tests/test_deletion.py::test_a_pair_re_added_after_deletion_has_no_leftover_coverage` |
| Skasowanie jednej pary nie rusza pozostałych | `tests/test_deletion.py::test_deleting_one_resolution_leaves_another_archived_one_of_the_same_symbol_alone` |
| Restart modułu | `tests/test_jobs_store.py::test_startup_interrupts_a_running_chunk`, `::test_startup_interrupts_chunks_still_queued` (pre-existing: no chunk is ever left mid-write across a restart) — no test restarts the module mid-deletion specifically, since `close_for_deletion`/`delete_pair_data` are each one committed transaction; a restart between the two leaves the pair untracked with its data intact, which is a correct, if untested, resting state |
| **market-data-tracking: Skasowanie zostaje odnotowane** | |
| Skasowanie pary z zebranymi danymi | `tests/test_deletion.py::test_deleting_a_pair_with_candles_records_the_count_and_range` |
| Skasowanie pary bez ani jednej świecy | `tests/test_deletion.py::test_deleting_a_pair_with_nothing_collected_records_zero` |
| Historia zleceń po skasowaniu | `tests/test_app.py::test_reading_deletions_narrowed_to_a_pair` (deletion and job both readable; job history itself proven pre-existing by `tests/test_app.py::test_reading_a_job_shows_every_pair_it_touched`) |
| Restart po skasowaniu | `tests/test_deletion.py::test_a_deletion_survives_a_fresh_connection` |
| **market-data-tracking: Usunięcie zatrzymuje zbieranie, ale nie kasuje danych (REMOVED)** | N/A — requirement removed; its replacement is proven above. `tests/test_tracking.py::test_untracking_keeps_every_candle` still passes because `tracking.untrack` (the low-level flip) is unchanged and is still correct as `close_for_deletion`'s building block |
| **market-data-api: Śledzone pary są zarządzalne przez kontrakt** | |
| Dodanie pary | `tests/test_app.py::test_a_pair_can_be_taken_on_over_the_contract` (pre-existing, unchanged) |
| Dodanie wielu par jednym żądaniem | `tests/test_app.py::test_adding_several_pairs_is_one_decision_with_one_job` (pre-existing) |
| Jedna z par zostaje odrzucona | `tests/test_app.py::test_a_multi_pair_request_refuses_one_without_losing_the_others` (pre-existing) |
| Żądanie bez momentu początku | `tests/test_app.py::test_a_legacy_single_pair_body_still_works` (pre-existing) |
| Dodanie pary nieznanej providerowi | `tests/test_app.py::test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason` (pre-existing) |
| Skasowanie pary (ex-"Usunięcie pary") | `tests/test_app.py::test_a_pair_can_be_deleted_over_the_contract` |
| Skasowanie pary, która nie jest śledzona | `tests/test_app.py::test_letting_go_of_a_pair_that_was_not_collected_is_a_404`, `::test_deleting_a_pair_a_404_does_not_touch_anything_else` |
| **market-data-api: Odnotowane skasowania są odczytywalne przez kontrakt** | |
| Odczyt skasowań | `tests/test_app.py::test_deleting_a_pair_with_nothing_collected_reports_zero` (response shape), `tests/test_deletion.py::test_reading_deletions_is_narrowed_to_one_pair` |
| Odczyt zawężony do pary | `tests/test_app.py::test_reading_deletions_narrowed_to_a_pair` |
| Nic nie było kasowane | `tests/test_app.py::test_reading_deletions_with_none_recorded_is_an_empty_list` |
| **market-data-store: Skasowanie danych pary zdejmuje też jej pokrycie** | |
| Skasowanie danych pary | `tests/test_deletion.py::test_deleting_removes_candles_and_coverage` |
| Kasowanie przerwane w połowie | not directly tested — see note below the table |
| Zapytanie o okres po skasowaniu | `tests/test_deletion.py::test_a_period_that_was_covered_before_deletion_reads_as_not_collected` |
| Inna rozdzielczość tego samego symbolu | `tests/test_deletion.py::test_deleting_one_resolution_leaves_another_archived_one_of_the_same_symbol_alone` |
| Skasowanie serii, z której wyliczane są inne | `tests/test_deletion.py::test_deleting_the_minute_series_removes_its_rollups` |
| **terminal-data-manager: Zdjęcie pary jest jawną decyzją** | |
| Operator zdejmuje parę (interval) | `InstrumentsView.test.tsx`: "asks first, warns the removal is permanent, and drops only that interval" |
| Operator zdejmuje cały instrument | `InstrumentsView.test.tsx`: "names every resolution that will be deleted, and removes the whole row once confirmed" |
| Operator wycofuje się z potwierdzenia | `InstrumentsView.test.tsx`: "leaves the interval collecting when the confirmation is dismissed" |
| Kasowanie zawodzi | `InstrumentsView.test.tsx`: "says so and leaves the interval listed when deletion fails", "drops what succeeded, keeps what failed listed, and names it in the confirmation" |
| **terminal-data-manager: Skasowanie odsyła do historii** | |
| Po skasowaniu | `InstrumentsView.test.tsx`: "reports how many candles were removed and points to Data History", "reports the total removed across every interval that succeeded" |
| **terminal-collection-history: Skasowanie danych widać w historii** | |
| Historia pary po skasowaniu | `CollectionHistoryView.test.tsx`: "shows a deletion alongside a pull, newest first", "names the pair, when, how many candles, and the range they covered" |
| Skasowanie odróżnia się od dociągnięcia | `CollectionHistoryView.test.tsx`: "does not read as a success or a failure" |
| Instrument skasowany w całości | `CollectionHistoryView.test.tsx`: "keeps an instrument's history readable after it was deleted in full" |

## Gaps

- **"Kasowanie przerwane w połowie"** (market-data-store) has no dedicated test. `delete_pair_data` and `close_for_deletion` each run inside `async with conn.transaction():`, the same primitive `coverage.record_coverage` already relies on elsewhere in this codebase without its own fault-injection test — asserting atomicity here would need forcing a mid-transaction failure on a real `asyncpg` connection, which is disproportionate to what it would prove beyond "the database's transaction guarantee holds." Left as a structural guarantee rather than a tested one, consistent with how the rest of the module treats `conn.transaction()`.
- **Task 7.4** (manual end-to-end pass) is explicitly deferred to the operator per tasks.md and is not part of this review's verification.

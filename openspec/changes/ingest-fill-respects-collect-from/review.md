## Verdict

Shipped in three passes, because the first two were wrong about the size of the problem and the
live stack said so both times.

1. **The quiet fill** (`ingest/backfill.py`'s `bars_to_close_gap`/`fill_gap`) now clamps to a
   pair's `collect_from` for a pair with nothing collected, instead of always reaching back the
   module's fixed `default_backfill_bars`. A pair tracked without an explicit `collect_from` is
   unaffected — its `collect_from` was already computed from that same default depth
   (`tracking.default_collect_from`). `periods_between` moved from `jobs/plan.py` to `periods.py`
   to give `ingest/backfill.py` a way to reach it without a circular import.
2. **The older edge is now a moment, not a count.** `GET /history` takes `after`; `collect` clamps
   its windows to it, stops paging at it, and drops anything older before building the answer. Both
   `market-data` callers pass it (`after=chunk.chunk_start`, `after=collect_from`) *and* filter what
   came back before writing.
3. **Reaching that floor is no longer reported as the provider's history ending.** Both ways
   `collect`'s loop can run out now settle that question through one shared `on_the_floor` check,
   and `history_ended = True` has a single assignment site.

Backend suites, lint, and `openspec validate --strict` are green in both modules.

Knowingly incomplete: task 7.4 (a manual pass on a running stack) is left for the operator, as
scoped — and this review is written *before* that pass, so it certifies the tests and the reasoning,
not the live outcome. Non-Goals in design.md are deliberate, not gaps: the quiet fill and the job
system still do redundant work fetching the same range for a wizard-added pair — harmless
(`write_candles` dedupes, `record_coverage` merges), and coordinating the two was explicitly out of
scope.

## Verified

- `cd modules/market-data && uv run pytest -q` → `415 passed, 7 skipped`
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `cd modules/capital-gateway && uv run pytest -q` → `140 passed, 8 skipped`
- `cd modules/capital-gateway && uv run ruff check .` → `All checks passed!`
- `cd modules/terminal && npm run test` → `221 passed` (untouched by this change; run because the
  branch carries the delete-dialog work alongside it)
- `openspec validate ingest-fill-respects-collect-from --strict` → valid
- Database state that opened pass 3, read directly rather than inferred:
  `collection_job_chunks` held `MINUTE_5 … done` for `2026-02-16 07:01 → 2026-08-08 21:41`
  (35 329 candles, 52 requests) and `MINUTE_5 … skipped` for `2026-01-01 → 2026-02-16 07:01`
  (0 candles, **0 requests**) — a bulk skip, not an empty fetch, which is what pointed at
  `history_ended` rather than at the paging arithmetic.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `capital_gateway/history.py` — no-progress branch | The first fix for the false `history_ended` guarded only the empty/`not-found` exit from the paging loop. The clamped last window does not usually come back empty: it comes back holding the same oldest candle again, which took the *other* exit and set `history_ended` anyway. This is the defect that survived into the second live test and cost six weeks of `5m` candles. | Fixed — both exits fall through to one terminal block; `history_ended` has one assignment site |
| Medium | `tests/test_ingest.py` — my own earlier review | `test_a_fill_for_a_pair_with_an_explicit_shallow_collect_from_does_not_reach_past_it` asserted only `bars == 30` against a `FakeHistory([])`. It pinned the *request* and never what was stored, so it could not have caught an overshoot — and the previous version of this review listed it as proving the spec's "MUST NOT zapisać ani jednej świecy starszej niż `collect_from`". That claim was too strong. | Fixed — `test_a_fill_stores_nothing_older_than_collect_from` and `test_a_chunk_stores_nothing_older_than_its_own_window` assert database contents |
| Low | `capital_gateway/tests/test_app.py` | While writing the route test I expected `from=2024-01-10` and got `2024-01-11T12:45`. My expectation was wrong, not the code: 1000 five-minute candles span ~3.5 days, so a floor five days back never clamps anything. | Fixed — floor moved so the clamp is actually exercised |

One thing worth naming rather than treating as a silent given: `periods_between`'s rounding is
`math.ceil`, so a clamped fill can still *request* a window starting up to just under one period
before `collect_from`. Not a finding — the write-side filter means nothing older than the floor is
stored regardless — but a reader should not read a bar count in a test as a promise about the exact
minute a window opens.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-ingest: Uzupełnianie wstecz sięga po historię** | |
| Nowo dodana para (no explicit `collect_from`) | `market-data tests/test_ingest.py::test_a_pair_that_has_nothing_reaches_back_the_default`, `::test_a_first_fill_reaches_back_the_configured_depth` |
| Nowo dodana para z jawną, płytszą datą OD | `::test_an_explicit_shallow_collect_from_clamps_below_the_default` (arithmetic), `::test_a_fill_stores_nothing_older_than_collect_from` (what lands in the database) |
| Provider nie ma starszych danych | `::test_the_end_of_provider_history_is_recorded_as_a_boundary` |
| **capital-market-data: Historia jest stronicowana poza limit providera** | |
| Prośba o więcej świec, niż mieści jedno żądanie | `capital-gateway tests/test_history.py::test_a_multi_page_read_returns_one_ordered_series` |
| Historia instrumentu się kończy | `::test_running_past_the_bottom_keeps_what_was_collected` |
| Okno nie przynosi nic nowego | `::test_a_window_with_no_progress_ends_the_loop` |
| Odczyt ograniczony momentem, nie liczbą | `::test_a_window_never_reaches_past_the_floor`, `::test_reaching_the_floor_stops_the_paging`, `::test_a_floor_drops_candles_older_than_it`, `tests/test_app.py::test_an_after_parameter_bounds_the_deep_read_in_the_past` |
| Okno przycięte do granicy konsumenta nic nie przynosi | `::test_an_empty_window_at_the_floor_is_not_the_end_of_history_either`, `::test_not_found_for_a_window_clamped_to_the_floor_is_not_an_ending`, `::test_no_progress_at_a_window_clamped_to_the_floor_is_not_an_ending` — one per way the loop can run out |
| Historia providera kończy się powyżej granicy konsumenta | `::test_running_out_of_provider_data_above_the_floor_still_ends_history` |
| **market-data-jobs: Kawałek jest ograniczony swoim oknem** | |
| Odpowiedź sięga poniżej okna kawałka | `market-data tests/test_jobs_runner.py::test_a_chunk_stores_nothing_older_than_its_own_window` |
| Interwał, w którym rynek stoi przez część tygodnia | Covered by the same test — the fake gateway returns candles below the window precisely because that is what a part-time market does to a bar count. The full-calendar version is task 7.4, on the live stack |
| **market-data-jobs: Kawałki pomija się w hurcie tylko na granicy providera** | |
| Kawałek zatrzymany na własnej krawędzi | `capital-gateway tests/test_history.py::test_no_progress_at_a_window_clamped_to_the_floor_is_not_an_ending` (the gateway never claims the ending) plus the pre-existing runner tests that only skip on `history_ended` |
| Provider kończy się w środku zakresu zlecenia | `market-data tests/test_jobs_runner.py` — pre-existing bulk-skip coverage, unchanged by this fix and deliberately still working |

Behaviors stated as MUST inside requirement prose rather than as their own scenario, proven anyway:

| Behavior | Proven by |
|---|---|
| A pair with no explicit `collect_from` is unaffected | `::test_a_pair_with_no_explicit_collect_from_is_unaffected` |
| `MAX_BARS_PER_FILL` still wins when `collect_from` is deeper than it | `::test_a_request_is_never_larger_than_the_gateway_accepts` |
| A pair not currently tracked requests nothing | `::test_a_fill_for_a_pair_no_longer_tracked_requests_nothing` |
| No floor leaves the read exactly as it was | `capital-gateway tests/test_history.py::test_no_floor_leaves_the_read_exactly_as_it_was` |

## Gaps

- **Task 7.4** (manual end-to-end pass on a running stack) is deferred to the operator and is not
  part of this review's verification. It is the only check that exercises a real session calendar;
  every test here uses a fake gateway whose "market closed" behaviour is one I wrote.
- The bulk-skip guard lives entirely in the gateway. `execute_chunk` still trusts
  `page.history_ended` without a second opinion, so a genuinely wrong ending from the provider would
  still skip queued chunks. Left as is — the gateway is where the information is — but named,
  because this is the mechanism that turned one wrong boolean into silent data loss twice.

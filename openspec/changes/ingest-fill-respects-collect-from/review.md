## Verdict

Shipped: the quiet gap-closing fill (`ingest/backfill.py`'s `bars_to_close_gap`/`fill_gap`) now
clamps to a pair's `collect_from` for a pair with nothing collected, instead of always reaching
back the module's fixed `default_backfill_bars`. A pair tracked without an explicit `collect_from`
is unaffected — its `collect_from` was already computed from that same default depth
(`tracking.default_collect_from`), so the clamp is a no-op for it. `periods_between` moved from
`jobs/plan.py` to `periods.py` to give `ingest/backfill.py` a way to reach it without a circular
import. Backend suite, lint, and `openspec validate --strict` are all green.

Knowingly incomplete: task 4.4 (a manual pass on a running stack, re-adding US100 with a shallow
`collect_from` and checking `Instruments`' „Data since") is left for the operator, as scoped.
Non-Goals in design.md are deliberate, not gaps: the quiet fill and the job system still do
redundant work fetching the same range for a wizard-added pair — harmless (`write_candles` dedupes,
`record_coverage` merges), and coordinating the two was explicitly out of scope for this fix.

## Verified

- `cd modules/market-data && uv run pytest -q` → `412 passed, 7 skipped`
- `cd modules/market-data && uv run ruff check .` → `All checks passed!`
- `openspec validate ingest-fill-respects-collect-from --strict` → `Change 'ingest-fill-respects-collect-from' is valid`

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| — | — | No findings survived verification. Every existing `fill_gap`/`PairIngest` test that needed a real `tracked_pairs` row to keep passing under the new `read_collect_from` dependency got one (`tests/test_ingest.py`'s new `_tracked()` helper); ran the full suite rather than trusting that by inspection. | — |

One thing worth naming rather than treating as a silent given: `periods_between`'s rounding is
`math.ceil` (its own docstring: "a safe overestimate rather than a guess that could come in
short"), so a clamped fill can still land up to just under one period before `collect_from`. Not
listed as a finding — this is the exact, already-accepted imprecision `design.md`'s Risks section
names, and one period is immaterial next to the years-deep bug this fixes — but a reader of this
review should not mistake `bars == 30` in
`test_a_fill_for_a_pair_with_an_explicit_shallow_collect_from_does_not_reach_past_it` for a promise
that every clamp lands on the exact minute.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-data-ingest: Uzupełnianie wstecz sięga po historię** | |
| Nowo dodana para (no explicit `collect_from`) | `tests/test_ingest.py::test_a_pair_that_has_nothing_reaches_back_the_default` (pure arithmetic), `::test_a_first_fill_reaches_back_the_configured_depth` (end-to-end: requests exactly `default_bars`) |
| Nowo dodana para z jawną, płytszą datą OD | `tests/test_ingest.py::test_an_explicit_shallow_collect_from_clamps_below_the_default` (pure arithmetic), `::test_a_fill_for_a_pair_with_an_explicit_shallow_collect_from_does_not_reach_past_it` (end-to-end — the incident, reproduced) |
| Provider nie ma starszych danych | `tests/test_ingest.py::test_the_end_of_provider_history_is_recorded_as_a_boundary` (pre-existing; `history_ended` handling is untouched by the clamp — a request for fewer bars than before can still discover the same boundary at whatever point it actually sits) |

Two behaviors this change adds that the spec states as MUST but names only inside the requirement
prose, not as their own scenario, are proven anyway:

| Behavior | Proven by |
|---|---|
| A pair with no explicit `collect_from` is unaffected (depth unchanged) | `tests/test_ingest.py::test_a_pair_with_no_explicit_collect_from_is_unaffected` |
| `MAX_BARS_PER_FILL` still wins when `collect_from` is deeper than it | `tests/test_ingest.py::test_a_request_is_never_larger_than_the_gateway_accepts` |
| A pair not currently tracked requests nothing, rather than falling back to the old depth | `tests/test_ingest.py::test_a_fill_for_a_pair_no_longer_tracked_requests_nothing` |

## Gaps

- **Task 4.4** (manual end-to-end pass on a running stack) is explicitly deferred to the operator
  per tasks.md and is not part of this review's verification.

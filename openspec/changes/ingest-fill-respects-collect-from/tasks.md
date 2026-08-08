## 1. market-data: `periods_between` moves to `periods.py`

- [x] 1.1 Move `periods_between` from `market_data/jobs/plan.py` to `market_data/periods.py`; update `jobs/plan.py` (definition site and its own use at line ~150) and `jobs/runner.py` to import it from `..periods`
- [x] 1.2 Move its tests from `tests/test_jobs_plan.py` to `tests/test_periods.py`, import updated (a third use in `test_jobs_plan.py`, asserting `split_into_windows`' own invariant, stays put — just re-imported from `market_data.periods`)
- [x] 1.3 `ruff` and the full `market-data` suite still pass — this step changes nothing behaviorally, only where the function lives (407 passed, 7 skipped)

## 2. market-data: `collect_from` reaches the quiet fill

- [x] 2.1 `tracking.read_collect_from(conn, symbol, resolution) -> datetime | None` — one query, `None` when the pair is not currently tracked
- [x] 2.2 `bars_to_close_gap` gains a required `collect_from: datetime` parameter; for `latest_candle is None` the result is clamped with `periods_between(resolution, collect_from, now)` alongside the existing `default_bars`/`MAX_BARS_PER_FILL` clamp
- [x] 2.3 `fill_gap` reads `collect_from` via `read_collect_from` in the same `pool.acquire()` block it already reads `latest_candle` in; `None` (pair no longer tracked) short-circuits to the existing "zero bars, nothing requested" outcome rather than calling `bars_to_close_gap` at all
- [x] 2.4 Tests for `bars_to_close_gap`: a pair with nothing collected and a `collect_from` shallower than `default_bars` asks for exactly enough bars to reach it, not `default_bars`; a pair with no explicit `collect_from` (i.e. one computed the same way `default_bars` would) is unaffected — same bar count as before this change; the `MAX_BARS_PER_FILL` ceiling still wins when `collect_from` is deeper than it
- [x] 2.5 Tests for `fill_gap`: end-to-end with a fake `GatewayHistory`, a pair tracked with an explicit shallow `collect_from` receives no candle older than it; a pair whose `read_collect_from` returns `None` mid-flight requests zero bars rather than falling back to `default_bars` — *discovered while doing this: `fill_gap`'s and `PairIngest`'s existing DB tests never actually tracked their pair in `tracked_pairs` (the `still_tracked` callback several of them use is a fake, disconnected from the table); every one of them needed a real tracked row added so `read_collect_from` has something to find, which the tests now do via a new `_tracked()` helper*

## 3. market-data: end-to-end proof of the reported bug

- [x] 3.1 A test at the `Ingest`/`PairIngest` level (or as close to `POST /pairs` as the module's existing test doubles allow) reproducing the incident: track a pair with an explicit `collect_from` shallower than `default_bars`, run the quiet fill, assert no candle lands before `collect_from` — the shape of test that would have caught this before it reached a running instance

## 4. Domknięcie

- [x] 4.1 `ruff` i `pytest` w `market-data` (412 passed, 7 skipped)
- [x] 4.2 README modułu: `ingest/backfill.py`'s section (or wherever `fill_gap`/quiet-fill behavior is documented) says it respects `collect_from`, not a bare configured depth
- [x] 4.3 `openspec validate ingest-fill-respects-collect-from --strict`
- [ ] 4.4 Ręczne potwierdzenie na uruchomionym zestawie: dodać parę z datą OD płytszą niż `default_backfill_bars` by dała, sprawdzić w `Instruments`' „Data since", że żaden interwał nie sięga głębiej niż wskazana data — *do ręcznego potwierdzenia przez operatora*

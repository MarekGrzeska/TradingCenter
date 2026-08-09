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

## 4. capital-gateway: granica w czasie, nie tylko w liczbie świec

*Otwarte przez pierwszy test na żywo: fill był już przycięty do `collect_from`, a dane nadal
sięgały miesiące za wskazaną datę. `bars` liczy świece, `periods_between` liczy okresy kalendarza —
dla instrumentu notowanego ~70% czasu różnią się o połowę. Żaden licznik tego nie naprawi.*

- [x] 4.1 `window_before` gains a `floor` parameter that raises the older edge of a window when the calendar-derived one would reach past it
- [x] 4.2 `collect` gains `after`: windows clamped to it, paging stopped once a page reaches it, candles older than it dropped before the answer is built (a page is clamped only at its edges, so one can still carry candles from below the floor)
- [x] 4.3 `adapter.get_history` gains `floor`; `GET /history` gains the `after` query parameter, documented in the route table and in a README section explaining why a count cannot say what `after` says
- [x] 4.4 Tests: a floor drops candles older than it; a window never reaches past the floor; reaching the floor stops the paging; no floor leaves the read byte-for-byte as it was; a route-level test that `after` bounds the deep read

## 5. capital-gateway: osiągnięcie granicy to nie koniec historii

*Otwarte przez drugi test na żywo, i to jest ten kosztowny. `history_ended` jest zapisywane jako
trwała granica instrumentu i uruchamia `skip_chunks_beyond_history` — kawałek `5m` na
2026-01-01 → 2026-02-16 skończył jako `skipped`, 0 żądań, bo nowszy kawałek fałszywie powiedział,
że dalej nic nie ma.*

- [x] 5.1 `reached_floor` jako osobny stan od `history_ended`; do odpowiedzi trafia wyłącznie ten drugi (`history_ended and not reached_floor and len(trimmed) < bars`)
- [x] 5.2 `on_the_floor` — „starsza krawędź tego okna to podłoga, nie kalendarz" — liczone raz na iterację, obok okna, które opisuje
- [x] 5.3 **Obie** drogi wyjścia z pętli (puste/`not-found` okno **oraz** okno bez postępu) schodzą do jednego wspólnego bloku końcowego; `history_ended = True` ma w funkcji jedno miejsce przypisania — *pierwsze podejście objęło tylko gałąź pustego okna i błąd przeżył do drugiego testu na żywo; to jest ta poprawka strukturalna, nie kosmetyczna*
- [x] 5.4 Testy obu dróg z osobna: `test_not_found_for_a_window_clamped_to_the_floor_is_not_an_ending` i `test_no_progress_at_a_window_clamped_to_the_floor_is_not_an_ending` (ten drugi odtwarza zmierzony kształt: stronicowanie staje na świecy 07:05, a 3½-minutowy odcinek poniżej oddaje tę samą świecę)
- [x] 5.5 Test, że granica wywołującego nie **ukrywa** prawdziwego końca historii: `test_running_out_of_provider_data_above_the_floor_still_ends_history`, z podłogą tak głęboką, że żadne okno nie jest do niej przycięte

## 6. market-data: obie ścieżki nazywają starszą krawędź i pilnują jej u siebie

- [x] 6.1 `gateway/history.py`: `history(...)` przekazuje `after` do trasy gatewaya
- [x] 6.2 `jobs/runner.py`: `execute_chunk` woła gateway z `before=chunk.chunk_end, after=chunk.chunk_start`
- [x] 6.3 `ingest/backfill.py`: `fill_gap` woła gateway z `after=collect_from`
- [x] 6.4 Obie ścieżki filtrują odpowiedź przed zapisem (`c.period_start >= <krawędź>`), zamiast ufać, że gateway granicy dotrzymał — obietnica o zawartości archiwum należy do tego modułu
- [x] 6.5 `refresh_all` po kawałku `MINUTE` liczone po tym, co zapisano, nie po tym, co przyszło — inaczej kubełek powstałby ze świec, których w archiwum nie ma
- [x] 6.6 Testy sprawdzające **zawartość bazy**, nie kształt żądania: `test_a_chunk_stores_nothing_older_than_its_own_window`, `test_a_fill_stores_nothing_older_than_collect_from` — *poprzedni test tej reguły asertował wyłącznie liczbę zamówionych barów przy pustej odpowiedzi, więc nie mógł tego złapać; to była luka w moim własnym review*

## 7. Domknięcie

- [x] 7.1 `ruff` i `pytest` w `market-data` (415 passed, 7 skipped) oraz w `capital-gateway` (140 passed, 8 skipped)
- [x] 7.2 README modułu: `ingest/backfill.py`'s section (or wherever `fill_gap`/quiet-fill behavior is documented) says it respects `collect_from`, not a bare configured depth
- [x] 7.3 `openspec validate ingest-fill-respects-collect-from --strict`
- [x] 7.4 Ręczne potwierdzenie na uruchomionym zestawie: wyczyścić archiwum, dodać US100 w `5m`–`1W` z datą OD 2026-01-01, sprawdzić w `Instruments`' „Data since", że żaden interwał nie sięga przed tę datę — w szczególności `5m`, oraz że w `collection_job_chunks` żaden kawałek nie jest `skipped` — *potwierdzone przez operatora 2026-08-09, za trzecim podejściem*

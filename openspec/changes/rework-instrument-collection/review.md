## Verdict

Zmiana weszła w całości: `capital-gateway` zawęża katalog do klasy i kotwiczy głęboki odczyt w
przeszłości, `market-data` ma trwałe zlecenia dociągania z planowaniem, wyceną, wykonaniem i
ponowieniem, a terminal ma połączoną zakładkę `Instruments` z kreatorem, nową zakładkę
`Data History` i slot wykresu przyjmujący wyłącznie instrumenty archiwizowane. Review znalazło
i naprawiło trzy defekty oraz trzy braki implementacyjne wobec specyfikacji — wszystkie opisane
niżej jako FIXED.

Świadomie niedomknięte: zadanie 12.2, przejście ścieżki end-to-end na uruchomionym zestawie,
zostało zostawione operatorowi do ręcznego potwierdzenia i nie zostało wykonane w tej sesji. Nie
jest to przeoczenie — cała logika ma pokrycie testowe wymienione niżej, ale żaden test nie
dotknął prawdziwego providera, więc pierwszy prawdziwy przebieg jest nadal przed tą zmianą.
Czego późniejszy czytelnik nie powinien brać za przeoczenie: postęp dla `DAY`/`WEEK` skacze z 0
na 100 (jeden kawałek to całe dziesięć lat — nie ma tam nic pośredniego do pokazania), a
`/archive` celowo nie przekierowuje nigdzie, tylko trafia na stronę „nie ma takiej zakładki".

## Verified

| Co uruchomione | Wynik |
|---|---|
| `uv run ruff check .` w `capital-gateway` | All checks passed! |
| `uv run pytest -q` w `capital-gateway` | 130 passed, 8 skipped |
| `uv run ruff check .` w `market-data` | All checks passed! |
| `uv run pytest -q` w `market-data` | 386 passed, 7 skipped |
| `pnpm lint` (eslint .) w `terminal` | bez zgłoszeń, kod wyjścia 0 |
| `pnpm typecheck` (tsc -b --noEmit) w `terminal` | bez błędów, kod wyjścia 0 |
| `pnpm test` (vitest run) w `terminal` | 16 plików, 203 passed |
| `openspec validate rework-instrument-collection --strict` | `Change 'rework-instrument-collection' is valid` |

Pominięte testy to te oznaczone `db`/live wymagające prawdziwego providera — tak samo jak przed tą
zmianą. **Nie uruchomiono** zestawu end-to-end (zadanie 12.2).

Jeden test sprawdzono mutacją, bo łatwo napisać taki, który przechodzi z powodu i bez powodu:
`Autocomplete.test.tsx::shows the result of the last query typed…` po usunięciu wartownika
`if (cancelled) return` z `useAsyncOptions` faktycznie pada, i przechodzi po jego przywróceniu.

## Findings

Wszystkie znalezione podczas review własnego diffu tej zmiany, wszystkie naprawione przed
napisaniem tego dokumentu.

| Severity | Where | Finding | Status |
|---|---|---|---|
| High | `market_data/jobs/runner.py:166` | Kawałek, którego wykonanie rzuciło wyjątkiem poza obsługą `GatewayError` w `execute_chunk` — zły zapis do bazy, błąd w module — zostawał w stanie `running` na zawsze. Żaden worker nie podejmuje kawałka `running` (`claim_pending_chunk` bierze tylko `pending`), `retry_job` go nie rusza (`RETRYABLE_CHUNK_STATES` to `failed`/`interrupted`), a `derive_status` czyta każdy otwarty kawałek jako zlecenie trwające. Skutek: zlecenie w `Data History` na wieki „w toku", z zamrożonym postępem, ponowienie odmawiane z 409, aż do restartu modułu. | FIXED w `5a59e29` — worker osadza taki kawałek jako `failed`, co czyni go ponawialnym; `_fail_orphan` jest best-effort, bo najczęstszą przyczyną jest sama baza |
| Medium | `market_data/app.py:552`, `:467` | `FutureRequest` z `plan_chunks` nie miał handlera, więc data OD w przyszłości spadała do handlera `Exception` i wracała jako 500 „the archive failed to answer this request" — o żądaniu, które było po prostu błędne. Specyfikacja `market-data-jobs`, „Data w przyszłości", wymaga odmowy nazywającej powód. Dodatkowo `POST /pairs` rzucał to *po* `add_pair` i `ingest.sync()`, więc odmowa zmieniała już to, co archiwum zbiera. | FIXED w `5a59e29` — handler zwraca 422 z powodem, a `POST /pairs` sprawdza datę przed dodaniem czegokolwiek, żeby odmowa nic nie kosztowała |
| Medium | `terminal/src/grid/GridView.tsx:97` | Slot pamiętający rozdzielczość, która przestała być archiwizowana, gdy symbol został — np. `US100 MINUTE_5` po zostawieniu tylko `HOUR_4` — rysował wykres pary, której nikt nie zbiera, a jego własny selektor, zawężony do archiwizowanych, pokazywał inną rozdzielczość. Dwa elementy interfejsu zaprzeczały sobie nawzajem. | FIXED w `5a59e29` — slot rozpoznaje to jako utratę ważności i proponuje rozdzielczości nadal zbierane, jednym kliknięciem |
| Low | `terminal/src/instruments/AddInstrumentWizard.tsx:189` | Dialog akceptacji trzymał wyceniane żądanie w `ref`, a wycenę pobierał w `useEffect([])`. Gdyby kiedykolwiek przerenderował się z nowym żądaniem bez odmontowania, pokazałby starą wycenę nad przyciskiem akceptującym nowe pary. Nieosiągalne dziś (overlay przechwytuje kliknięcia), ale niejawnie. | FIXED w `5a59e29` — dialog jest kluczowany na żądaniu, więc „jeden dialog na jedno żądanie" jest niezmiennikiem strukturalnym, nie przypadkiem |
| Medium | `terminal/src/instruments/AddInstrumentWizard.tsx:139` | Podpowiedź instrumentu pokazywała tylko symbol i nazwę. `terminal-instruments`, „Instrumenty wyszukuje się po frazie", wymaga MUST także klasy aktywów i informacji o handlowalności, oraz bid/ask tam, gdzie źródło je podaje — to zniknęło przy zamianie przeglądarki katalogu na podpowiedzi. | FIXED w `d2c89dd` |
| Medium | `terminal/src/ui/Autocomplete.tsx:180` | Wyliczenie nieucięte nie podawało liczby instrumentów, czego wymaga `terminal-instruments`, „Katalog kompletny" — a operator podejmuje na tej liście decyzję o dziesiątkach minut dociągania, więc „to jest wszystko" jest częścią tej decyzji. | FIXED w `d2c89dd` — `countLabel` pokazywany tylko gdy nic nie ucięto; liczba pod listą uciętą czytałaby się jak całość |
| Low | `terminal/src/instruments/AddInstrumentWizard.tsx:399` | design.md, „Wycena liczy kawałki, a nie osobną formułę", rozstrzygnął, że dialog powie wprost, iż liczby są szacunkiem zawyżonym o okresy zamkniętego rynku. Nie mówił tego. | FIXED w `975db5c` |

Rozważone i **nie** zgłoszone jako defekt: `list_jobs` czyta każde zlecenie osobnym `read_job`
(N+1 zapytań). Przy odpytywaniu co 10 s i limicie `MAX_TRACKED_PAIRS` to zapytania do własnej
bazy w liczbie rzędu dziesiątek — realne, ale nie na tyle, by przerabiać to zanim zaboli.

## Spec coverage

### capital-market-data

| Requirement / Scenario | Proven by |
|---|---|
| Instrumenty są wyszukiwalne i wyliczalne | — |
| · Wyszukiwanie po frazie | `tests/test_adapter.py::test_searching_returns_matching_instruments` |
| · Wyliczenie katalogu | `tests/test_adapter.py::test_the_traversal_dedupes_and_survives_a_bad_branch` |
| · Wyliczenie jednej klasy aktywów | `tests/test_adapter.py::test_one_asset_class_comes_back_without_the_others`, `::test_filtering_by_class_still_walks_the_whole_tree`, `::test_a_class_nothing_matches_is_an_empty_catalogue_not_an_error`, `::test_a_filtered_walk_cut_short_still_says_so` |
| · Klasa aktywów spoza znanych | `tests/test_app.py::test_an_unknown_asset_class_is_refused_by_naming_the_known_ones` |
| · Odczyt zbioru klas aktywów | `tests/test_app.py::test_the_asset_classes_are_published` |
| · Gałąź katalogu jest nieczytelna | `tests/test_adapter.py::test_the_traversal_dedupes_and_survives_a_bad_branch` |
| Głęboki odczyt zaczyna się w dowolnym momencie | — |
| · Odczyt zakotwiczony w przeszłości | `tests/test_history.py::test_an_anchor_shapes_only_the_first_page`, `tests/test_app.py::test_a_before_parameter_anchors_the_deep_read_in_the_past` |
| · Odczyt bez wskazanego momentu | `tests/test_history.py::test_no_anchor_keeps_reaching_back_from_now` |

### market-data-api

| Requirement / Scenario | Proven by |
|---|---|
| Śledzone pary są zarządzalne przez kontrakt | — |
| · Dodanie pary | `tests/test_app.py::test_a_legacy_single_pair_body_still_works` |
| · Dodanie wielu par jednym żądaniem | `tests/test_app.py::test_adding_several_pairs_is_one_decision_with_one_job` |
| · Jedna z par zostaje odrzucona | `tests/test_app.py::test_a_multi_pair_request_refuses_one_without_losing_the_others` |
| · Żądanie bez momentu początku | `tests/test_app.py::test_a_legacy_single_pair_body_still_works`, `tests/test_tracking.py::test_a_pair_tracked_without_a_moment_gets_the_default_depth` |
| · Dodanie pary nieznanej providerowi | `tests/test_app.py::test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason` |
| · Usunięcie pary | `tests/test_app.py::test_letting_go_of_a_pair_that_was_not_collected_is_a_404`, `tests/test_tracking.py::test_untracking_keeps_every_candle` |
| Kontrakt wycenia zlecenie przed jego złożeniem | — |
| · Odczyt wyceny | `tests/test_app.py::test_estimating_prices_pairs_without_creating_anything` |
| · Wycena nie ma skutków ubocznych | `tests/test_app.py::test_estimating_prices_pairs_without_creating_anything` (sprawdza, że `/pairs` zostaje puste), `tests/test_jobs_plan.py::test_estimating_has_no_side_effects` |
| · Wycena pary nieznanej providerowi | `tests/test_app.py::test_estimating_names_a_symbol_the_gateway_does_not_know` |
| Zlecenia dociągania są odczytywalne przez kontrakt | — |
| · Odczyt zleceń pary | `tests/test_app.py::test_listing_jobs_filtered_to_one_pair`, `::test_listing_jobs_narrows_to_one_row_per_pair` |
| · Odczyt zlecenia w toku | `tests/test_app.py::test_reading_a_running_job_carries_its_progress_and_the_pair_in_flight` |
| · Odczyt zlecenia zakończonego częściowo | `tests/test_app.py::test_reading_a_partly_failed_job_says_partial_and_names_each_failure` |
| Nieudane zlecenie da się ponowić przez kontrakt | — |
| · Ponowienie nieudanego zlecenia | `tests/test_app.py::test_retrying_a_failed_job_resets_only_it_and_wakes_the_runner` |
| · Ponowienie zlecenia bez porażek | `tests/test_app.py::test_retrying_wakes_the_runner_and_is_refused_with_nothing_to_retry` |
| · Ponowienie zlecenia nieistniejącego | `tests/test_app.py::test_retrying_an_unknown_job_is_404` |

### market-data-ingest

| Requirement / Scenario | Proven by |
|---|---|
| Uzupełnianie wstecz sięga po historię | — |
| · Nowo dodana para | `tests/test_ingest.py::test_a_first_fill_reaches_back_the_configured_depth` |
| · Kawałek to jedno żądanie | `tests/test_ingest.py::test_a_fill_is_one_request_however_deep`, `tests/test_jobs_runner.py::test_the_request_is_anchored_on_the_chunk_end` |
| · Provider nie ma starszych danych | `tests/test_ingest.py::test_the_end_of_provider_history_is_recorded_as_a_boundary` |
| Ingest raportuje swój postęp i porażki | — |
| · Uzupełnianie się kończy | `tests/test_ingest.py::test_a_fill_records_what_it_verified`, `::test_the_supervisor_reports_what_each_fill_did` |
| · Uzupełnianie zawodzi | `tests/test_ingest.py::test_a_failed_fill_names_its_reason_and_does_not_raise`, `tests/test_jobs_runner.py::test_a_failed_chunk_does_not_raise_out_of_execute_chunk` |
| · Raport po restarcie | `tests/test_jobs_store.py::test_startup_interrupts_a_running_chunk`, `::test_startup_interrupts_chunks_still_queued`, `::test_settled_chunks_are_untouched_by_a_restart` |

### market-data-jobs

| Requirement / Scenario | Proven by |
|---|---|
| Zlecenie jest jednostką decyzji, kawałek jednostką pracy | — |
| · Zlecenie na wiele par | `tests/test_app.py::test_adding_several_pairs_is_one_decision_with_one_job`, `tests/test_jobs_store.py::test_a_job_spanning_two_pairs_reads_whole_through_read_job` |
| · Zakres głębszy niż jedno żądanie | `tests/test_jobs_plan.py::test_a_wide_gap_splits_at_the_bars_ceiling`, `::test_windows_never_exceed_the_bars_ceiling` |
| · Para już pokryta | `tests/test_jobs_plan.py::test_a_fully_covered_pair_plans_nothing`, `::test_a_partly_covered_pair_plans_only_the_gap` |
| Data OD jest przycinana do tego, co provider ma | — |
| · Data sprzed historii providera | `tests/test_jobs_plan.py::test_a_moment_before_provider_history_is_clipped_not_refused`, `::test_a_clipped_pair_says_so_in_its_estimate` |
| · Data w przyszłości | `tests/test_jobs_plan.py::test_a_future_request_is_refused`, `tests/test_app.py::test_estimating_from_a_future_date_is_refused_with_the_reason`, `::test_tracking_from_a_future_date_is_refused_and_tracks_nothing` |
| Zlecenie da się wycenić przed jego uruchomieniem | — |
| · Wycena przed decyzją | `tests/test_jobs_plan.py::test_an_estimate_prices_every_pair_and_sums_them`, `tests/test_app.py::test_estimating_prices_pairs_without_creating_anything` |
| · Szacunek jest opisany jako szacunek | `terminal/src/instruments/AddInstrumentWizard.test.tsx::says the numbers are estimates and why the real count comes in lower` |
| Postęp zlecenia jest mierzony, nie zgadywany | — |
| · Odczyt postępu w trakcie | `tests/test_app.py::test_reading_a_running_job_carries_its_progress_and_the_pair_in_flight` |
| · Długi kawałek | `tests/test_jobs_store.py::test_a_partial_job_names_the_pair_still_running` (postęp liczony z kawałków osiadłych, więc trwający go nie podnosi) |
| Nieudany kawałek nie przerywa zlecenia | — |
| · Kawałek w środku zakresu zawodzi | `tests/test_jobs_runner.py::test_a_refusal_settles_the_chunk_as_failed_with_the_reason`, `::test_a_worker_keeps_going_after_one_chunk_raises` |
| · Zlecenie kończy się częściowo | `tests/test_jobs_store.py::test_a_mix_of_done_and_failed_is_partial`, `tests/test_app.py::test_reading_a_partly_failed_job_says_partial_and_names_each_failure` |
| · Pokrycie z luką | `tests/test_jobs_runner.py::test_the_full_window_is_recorded_as_covered_not_only_where_candles_landed` |
| Ponowienie obejmuje wyłącznie to, co zawiodło | — |
| · Ponowienie po porażce części | `tests/test_jobs_store.py::test_retrying_resets_only_failed_and_interrupted_chunks`, `tests/test_app.py::test_retrying_a_failed_job_resets_only_it_and_wakes_the_runner` |
| · Ponowienie się udaje | `tests/test_jobs_store.py::test_retrying_bumps_the_reset_chunks_attempt`, `tests/test_jobs_runner.py::test_the_runner_claims_and_settles_a_pending_chunk` |
| · Ponowienie zlecenia bez porażek | `tests/test_jobs_store.py::test_retrying_a_job_with_nothing_failed_is_refused` |
| Historia zleceń przeżywa restart | — |
| · Odczyt po restarcie | `tests/test_jobs_store.py::test_settled_chunks_are_untouched_by_a_restart` |
| · Zlecenie przerwane zatrzymaniem | `tests/test_jobs_store.py::test_startup_interrupts_a_running_chunk`, `::test_startup_interrupts_chunks_still_queued` |
| Zlecenia dzielą budżet ruchu z resztą modułu | — |
| · Kilka zleceń naraz | `tests/test_ingest.py::test_a_supplied_limiter_is_used_instead_of_a_private_one` — **luka częściowa, patrz Gaps** |
| · Odczyt w trakcie zlecenia | **luka, patrz Gaps** |

### market-data-tracking

| Requirement / Scenario | Proven by |
|---|---|
| Śledzona para jest decyzją operatora | — |
| · Zapytanie o nieśledzoną parę | `tests/test_app.py::test_subscribing_to_a_pair_nobody_collects_is_refused` |
| · Operator dodaje parę | `tests/test_tracking.py::test_a_tracked_pair_reads_back` |
| · Operator dodaje instrument w kilku rozdzielczościach | `tests/test_tracking.py::test_a_symbol_at_two_resolutions_is_two_pairs`, `tests/test_app.py::test_adding_several_pairs_is_one_decision_with_one_job` |
| · Część decyzji zostaje odrzucona | `tests/test_app.py::test_a_multi_pair_request_refuses_one_without_losing_the_others`, `tests/test_tracking.py::test_the_pairs_already_tracked_are_untouched_by_a_refusal` |
| Śledzone pary są wyliczalne wraz ze swoim stanem | — |
| · Odczyt listy śledzonych par | `tests/test_tracking.py::test_the_status_carries_the_newest_candle`, `::test_a_pair_that_has_collected_nothing_still_appears` |
| · Zbieranie ustało po cichu | `tests/test_tracking.py::test_the_status_reports_collection_stalled_when_the_market_is_open`, `::test_the_status_does_not_call_a_shut_market_a_fault` |
| Para niesie moment, od którego ma być pokryta | — |
| · Para dodana z datą początku | `tests/test_tracking.py::test_a_pair_tracked_with_an_explicit_moment_keeps_it`, `tests/test_app.py::test_pairs_carry_collect_from` |
| · Para dodana bez daty początku | `tests/test_tracking.py::test_a_pair_tracked_without_a_moment_gets_the_default_depth`, `::test_default_collect_from_is_default_bars_back` |
| · Restart modułu | `tests/test_tracking.py::test_the_configuration_survives_a_restart`, `tests/test_schema.py::test_a_tracked_pair_carries_where_its_collection_starts` |
| · Ponowne dodanie pary z wcześniejszą datą | `tests/test_tracking.py::test_re_tracking_with_an_earlier_moment_pulls_collect_from_back`, `::test_re_tracking_with_a_later_moment_does_not_abandon_history` |

### terminal-instruments

| Requirement / Scenario | Proven by |
|---|---|
| Instrumenty wyszukuje się po frazie | — |
| · Wyszukiwanie po frazie | `AddInstrumentWizard.test.tsx::shows symbol, name, class, the spread and tradeability for each suggestion` |
| · Wyszukiwanie zawężone do klasy | `autocompleteSources.test.ts::searches within the class once a query is typed, and never truncates`, `data/gatewaySource.test.ts::narrows to the asset class client-side, since the gateway does not filter search` |
| · Fraza bez wyników | `Autocomplete.test.tsx::says plainly that nothing matched, rather than an empty list` |
| · Wyszukiwanie zawodzi | `Autocomplete.test.tsx::names a source failure and offers a retry that re-issues the fetch` |
| · Pisanie w polu wyszukiwania | `Autocomplete.test.tsx::does not issue a request per keystroke`, `::shows the result of the last query typed, even when an earlier answer lands later` |
| Katalog instrumentów mówi, gdy jest niepełny | — |
| · Wyliczenie instrumentów klasy | `autocompleteSources.test.ts::enumerates the class on an empty query, carrying the gateway's truncated flag` |
| · Katalog ucięty | `Autocomplete.test.tsx::says when the list was cut short, and that typing narrows it further`, `AddInstrumentWizard.test.tsx::warns instead of counting when the class was cut short` |
| · Katalog kompletny | `AddInstrumentWizard.test.tsx::states the instrument count when the class was enumerated whole` |
| Podpowiadanie zachowuje się wszędzie tak samo | — |
| · Wybór z klawiatury | `Autocomplete.test.tsx::picks the first, already-highlighted option on Enter alone`, `::moves the highlight with ArrowDown before Enter picks it`, `::does not move highlight above the first option`, oraz trzy testy „identical keyboard behavior across all three real sources" (`asset classes`, `instruments in a class`, `archived instruments`) |
| · Rezygnacja z wyboru | `Autocomplete.test.tsx::closes suggestions on Escape and leaves the prior choice untouched` |
| · Cofnięcie dokonanego wyboru | `Autocomplete.test.tsx::shows the current selection and clears it without an input remount losing state` |
| Klasy aktywów są wyliczalne | — |
| · Wybór klasy | `autocompleteSources.test.ts::returns every class on an empty query`, `Autocomplete.test.tsx::asset classes` |
| · Klasa spoza listy | `autocompleteSources.test.ts::filters locally by substring, case-insensitively` + `Autocomplete.test.tsx::says plainly that nothing matched…` (klasa spoza listy nie daje dopasowań, a instrument pozostaje zablokowany) |
| REMOVED: Wynik wyszukiwania trafia do slotu | usunięte wraz z `gridStore.assignToActiveSlot` i jego testem (`3f76aff`) |

### terminal-data-manager

| Requirement / Scenario | Proven by |
|---|---|
| Panel jest zakładką terminala | — |
| · Operator otwiera panel | `App.test.tsx::switching tabs updates both the content and the address` |
| · Odświeżenie strony | `App.test.tsx::loading an address directly shows that tab, not the default` |
| · Zakładki mówiące o instrumentach | `App.test.tsx::offers exactly one instruments tab and no catalogue or archive tab beside it`, `::sends a stale /archive bookmark to the unknown-tab page, not a tab` |
| Panel pokazuje, czy zbieranie działa | — |
| · Przegląd listy | `InstrumentsView.test.tsx::puts every resolution of the same instrument in one row, abbreviated`, `::shows the earliest addition among its resolutions as when archiving began` |
| · Instrument w wielu interwałach | `InstrumentsView.test.tsx::puts every resolution of the same instrument in one row, abbreviated` |
| · Zbieranie ustało | `InstrumentsView.test.tsx::marks the row and the stalled interval out from the rest`, `::does not mark an instrument whose resolutions are all healthy` |
| · Świeżość danych | `InstrumentsView.test.tsx::gives the newest collected candle for each interval` |
| Panel pokazuje zasięg archiwum | — |
| · Podgląd pokrycia pary | `InstrumentsView.test.tsx::shows coverage for every resolution once the row is expanded` |
| · Pokrycie z lukami | `InstrumentsView.test.tsx::names the gaps when coverage is more than one stretch`, `::says nothing is verified rather than showing an empty range` |
| Zdjęcie pary jest jawną decyzją | — |
| · Operator zdejmuje parę | `InstrumentsView.test.tsx::asks first, promises the candles stay, and drops only that interval`, `::leaves the interval collecting when the confirmation is dismissed` |
| · Operator zdejmuje cały instrument | `InstrumentsView.test.tsx::names every resolution that will stop, and removes the whole row once confirmed` |
| Instrumenty dokłada się kreatorem | — |
| · Przejście przez kreator | `AddInstrumentWizard.test.tsx::prices every pair, shows the range and a total, and asks for one estimate covering both resolutions` |
| · Instrumenty zależą od klasy | `autocompleteSources.test.ts::enumerates the class on an empty query…`, `::searches within the class once a query is typed…` |
| · Zmiana klasy po wybraniu instrumentu | `AddInstrumentWizard.test.tsx::clears the chosen instrument when the asset class changes` |
| · Podana data jest wcześniejsza niż historia providera | `tests/test_jobs_plan.py::test_a_moment_before_provider_history_is_clipped_not_refused` (przycięcie po stronie archiwum; kreator nie waliduje daty w ogóle, a domyślnie proponuje początek bieżącego roku — `AddInstrumentWizard.test.tsx::starts at the beginning of the current year, not at everything the provider has`) — **luka po stronie terminala, patrz Gaps** |
| · Kreator bez kompletu wyborów | `AddInstrumentWizard.test.tsx::blocks review until an instrument and at least one resolution are chosen` |
| Zatwierdzenie kreatora otwiera dialog akceptacji | — |
| · Dialog przed dodaniem | `AddInstrumentWizard.test.tsx::prices every pair, shows the range and a total, and asks for one estimate covering both resolutions` |
| · Zakres przycięty do historii providera | `AddInstrumentWizard.test.tsx::marks a clipped range and a pair already being collected` |
| · Operator odrzuca dialog | `AddInstrumentWizard.test.tsx::adds nothing and keeps the wizard's choices when the dialog is dismissed` |
| · Operator akceptuje | `AddInstrumentWizard.test.tsx::starts collection, lists what is now archiving, points to Data History, and resets the wizard` |
| · Wyceny nie da się pobrać | `AddInstrumentWizard.test.tsx::blocks acceptance and adds nothing when the estimate fails` |
| · Para już archiwizowana | `AddInstrumentWizard.test.tsx::marks a clipped range and a pair already being collected` |
| · Archiwum odmawia dodania | `AddInstrumentWizard.test.tsx::shows a refusal without hiding the pairs that were accepted` |
| REMOVED: Operator dokłada parę wybierając instrument i rozdzielczość | stary `ArchiveView` i jego testy usunięte w `723e464` |

### terminal-collection-history

| Requirement / Scenario | Proven by |
|---|---|
| Historia dociągania jest zakładką terminala | — |
| · Operator otwiera zakładkę | `App.test.tsx::switching tabs updates both the content and the address` |
| · Odświeżenie strony | `App.test.tsx::comes back to Data History on a reload rather than the default tab` |
| Widok jest per instrument i per interwał | — |
| · Instrument w kilku interwałach | `CollectionHistoryView.test.tsx::shows every resolution of the same instrument as its own row` |
| · Wiele dociągnięć tej samej pary | `CollectionHistoryView.test.tsx::shows multiple pulls of the same pair, newest first` |
| Praca w toku pokazuje mierzony postęp | — |
| · Zlecenie w toku | `CollectionHistoryView.test.tsx::shows a measured share of chunks done and candles written so far for a running job` |
| · Postęp stoi | `CollectionHistoryView.test.tsx::shows a measured share of chunks done…` (udział liczony z kawałków osiadłych) — **luka częściowa, patrz Gaps** |
| Zakładka odświeża się sama | — |
| · Operator patrzy na trwające zlecenie | `CollectionHistoryView.test.tsx::refreshes on its own every 10 seconds, and stops once the tab is left` |
| · Nieudane odświeżenie | `CollectionHistoryView.test.tsx::keeps the rows on screen when a refresh fails, and says the refresh failed` |
| · Operator przechodzi na inną zakładkę | `CollectionHistoryView.test.tsx::refreshes on its own every 10 seconds, and stops once the tab is left` |
| Zakończone dociąganie jest wyraźnie zakończone | — |
| · Wszystko się udało | `CollectionHistoryView.test.tsx::marks a full success distinctly, with candles and the covered range` |
| · Pokrycie częściowe | `CollectionHistoryView.test.tsx::marks partial coverage as its own state, and lists the failure reasons` |
| Nieudane dociąganie ponawia się z zakładki | — |
| · Operator ponawia | `CollectionHistoryView.test.tsx::says what will be retried before doing it, and moves the row to running once queued`, `::does not offer retry for a fully succeeded pull` |
| · Ponowienie samo zawodzi | `CollectionHistoryView.test.tsx::leaves the row as failed, not running, when the retry request itself fails` |
| Zakładka odróżnia brak historii od braku odpowiedzi | — |
| · Archiwum nieosiągalne | `CollectionHistoryView.test.tsx::tells an unreachable archive apart from an empty history` |
| · Nic jeszcze nie dociągano | `CollectionHistoryView.test.tsx::says nothing has been collected yet, and points to Instruments` |

### terminal-grid

| Requirement / Scenario | Proven by |
|---|---|
| Slot ma własny instrument i własny interwał | — |
| · Ten sam instrument w kilku interwałach | `GridView.test.tsx::changes one slot's resolution without disturbing the others`, `gridStore.test.ts` (stan slotów) |
| · Rozdzielczości do wyboru w slocie | `GridView.test.tsx::limits the resolution selector to what the instrument is archived in` |
| · Slot pusty | `GridView.test.tsx::invites a choice in an empty slot instead of drawing an empty chart` |
| Slot przyjmuje wyłącznie instrument archiwizowany | — |
| · Wybór instrumentu do slotu | `GridView.test.tsx::changes one slot's instrument without disturbing the others`, `Autocomplete.test.tsx::archived instruments` |
| · Instrument spoza archiwizowanych | `autocompleteSources.test.ts::filters locally by symbol, case-insensitively` + `GridView.test.tsx::says nothing archived matches, and points to Instruments, when the picker is empty` |
| · Nic nie jest archiwizowane | `GridView.test.tsx::says nothing archived matches, and points to Instruments, when the picker is empty`, `autocompleteSources.test.ts::reads an empty archive as no options, not a failure` |
| · Listy archiwizowanych nie da się odczytać | `GridView.test.tsx::keeps a slot's instrument when the archived list can't be read, and lets the picker say so` |
| Slot zapamiętany traci ważność, gdy instrument przestaje być archiwizowany | — |
| · Zapamiętany instrument został zdjęty z archiwizowanych | `GridView.test.tsx::recognizes a remembered instrument that stopped being archived, leaving other slots alone`, `::recognizes a remembered resolution that stopped being archived, and offers the ones left` |

## Gaps

Scenariusze bez własnego testu albo pokryte tylko pośrednio, oraz to, co odroczono. Żaden nie
blokuje archiwizacji zmiany; każdy jest świadomym pozostawieniem, nie przeoczeniem.

- **`market-data-jobs`, „Kilka zleceń naraz"** — że kawałki wykonują się kolejno pod
  skonfigurowaną równoległością, a nie wszystkie naraz. Dowiedzione jest, że `Ingest` i `JobRunner`
  dostają *ten sam* semafor (`test_ingest.py::test_a_supplied_limiter_is_used_instead_of_a_private_one`,
  `test_jobs_runner.py` konstruuje runner z podanym semaforem), ale żaden test nie liczy
  równoczesnych kawałków tak, jak `test_fills_do_not_run_more_at_once_than_the_budget_allows`
  liczy równoczesne fille. Test na to byłby wart dołożenia.
- **`market-data-jobs`, „Odczyt w trakcie zlecenia"** — że odczyt świec nie czeka na zlecenie.
  Prawdziwe konstrukcyjnie (odczyty idą do własnej bazy, kawałki do gatewaya, jedyny wspólny
  zasób to semafor, którego odczyt nie bierze), ale niesprawdzone.
- **`market-data-jobs`, „Długi kawałek"** i **`terminal-collection-history`, „Postęp stoi"** —
  połowa „postęp nie rośnie" wynika z definicji (`_progress` liczy tylko kawałki osiadłe) i nie ma
  testu wprost pokazującego dwa odczyty z tym samym udziałem.
- **`terminal-data-manager`, „Podana data jest wcześniejsza niż historia providera"** — kreator
  celowo nie waliduje daty OD w ogóle, więc „nie odrzuca jej jako błędnej" jest spełnione przez
  brak kodu. Przycięcie jest sprawdzone po stronie archiwum
  (`test_jobs_plan.py::test_a_moment_before_provider_history_is_clipped_not_refused`) i widoczne w
  dialogu (`marks a clipped range…`), ale nie ma testu terminala mówiącego „rok 1850 przechodzi
  przez kreator bez błędu walidacji".
- **Zadanie 12.2, ścieżka end-to-end** — przeszła częściowo, na żywo, 2026-08-09: dodanie
  instrumentu w interwałach `5m`–`1W` od zadanej daty, dialog akceptacji, zlecenie i podgląd
  postępu potwierdzone przez operatora wielokrotnie (US100). **Wymuszona porażka kawałka
  i ponowienie pozostają nieprzejściowane na uruchomionym zestawie** — pokryte wyłącznie testami
  z podstawionym gatewayem, i to jest jedyna noga tej ścieżki, o której wiadomo tyle, ile mówią
  testy.

  Warto to czytać w kontekście tego, co te przejścia na żywo faktycznie wykryły: trzy błędy
  w głębokości pobierania, których cały zielony pakiet testów nie złapał, bo podstawiony gateway
  zamykał rynek tak, jak napisał go autor testu (`ingest-fill-respects-collect-from`, review.md).
  Ścieżka porażki i ponowienia ma dziś dokładnie ten sam status, jaki miała wtedy ścieżka
  głębokości.

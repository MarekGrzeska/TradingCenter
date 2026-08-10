## Verdict

Trzy błędy produkcyjne naprawione i potwierdzone na produkcji przez operatora: granica
historii powstaje teraz z pomiaru i daje się unieważnić głębszą prośbą, `DAY` i `WEEK` mają
świecę w budowie od pierwszego kwotowania, a archiwum przestało utrwalać okres, który
jeszcze trwa. Pomiar `live` z grupy 1 został uruchomiony i wypadł po stronie, którą projekt zakładał:
provider oddaje bieżący, niedomknięty okres, więc zasiew i oznaczanie świecy w budowie
chodzą główną gałęzią. Czego nie brać za przeoczenie: `PairEstimate.clipped`
nie jest już przez nic ustawiane i to jest zamierzone (patrz Gaps), a wdrożenie odbyło się
w złej kolejności i położyło produkcję — opis niżej, bo to jest lekcja tej zmiany, nie
przypis do niej.

## Verified

Uruchomione lokalnie na końcowym stanie kodu:

| Komenda | Wynik |
|---|---|
| `capital-gateway` · `uv run pytest -q` | 185 passed, 11 skipped |
| `capital-gateway` · `uv run ruff check .` / `uv run pyright` | clean / 0 errors |
| `market-data` · `uv run pytest -q` | 536 passed, 7 skipped |
| `market-data` · `uv run pytest -m db -q` | 305 passed, 7 skipped, 231 deselected |
| `market-data` · `uv run ruff check .` / `uv run pyright` | clean / 0 errors |
| `terminal` · `pnpm test` | 287 passed (21 plików) |
| `terminal` · `pnpm lint` / `typecheck` / `contract:check` | clean / clean / up to date |
| `openspec validate … --strict` | valid |
| migracja | round-trip `0006 → 0007 → 0006` na bazie deweloperskiej |

`uv run pytest -m live --run-live` → **8 passed, 196 deselected**, uruchomione 10 sierpnia
przeciwko koncie demo. Potwierdziło trzy rzeczy, na których stoi ta zmiana, a których nikt
wcześniej nie zmierzył: najnowsza świeca odczytu `MINUTE_5` sięgającego teraźniejszości
pokrywa się z bieżącym kubełkiem (czyli błąd 3 był realny), odczyt `DAY` przy otwartym
rynku zawiera dzisiejszą świecę (czyli zasiew ma z czego wystartować), a `marketStatus`
zgadza się z tym, czy płyną kwotowania (czyli jest użytecznym źródłem prawdy dla `DAY`
i `WEEK`).

Uruchomienie zerwało sesję produkcyjnego gatewaya, jak zapowiadano. Wrócił sam, dzięki
osobnej poprawce wdrożonej w tym celu wcześniej (PR #49) — sprawdzone w bazie: zapisy
świec szły dalej pięć minut po pomiarze.

Na produkcji: po ręcznej migracji operator potwierdził, że kreator wycenia, wykres na `DAY`
i `WEEK` pokazuje ruchomą świecę bieżącą, a dociąganie starszej historii działa.

## Findings

Wszystkie z przeglądu gałęzi przed scaleniem, wszystkie naprawione przed wdrożeniem.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `stream/hub.py:95` | Zerwanie feedu w środku okresu gasiło świecę `DAY`/`WEEK` do końca doby. `invalidate()` i `on_sealed()` ustawiały ten sam stan, a te dwie sytuacje potrzebują przeciwnych odpowiedzi na pytanie, czy provider oddający **ten sam** okres to postęp. Blip trwający sekundy kosztował dobę wykresu. | FIXED `3e27170` |
| Wysoka | `routers/pairs.py:158` | Każde ponowne dodanie pary zdejmowało granicę, nie tylko prośba głębsza — warunek czytał `pair.collect_from`, czyli `LEAST(existing, new)`, więc dodanie bez daty wyglądało jak prośba głębsza. | FIXED `3e27170` |
| Średnia | `stream/hub.py:214` | Dołączający subskrybent dostawał świecę zamkniętą oznaczoną `forming`, w oknie między zapieczętowaniem a kolejnym odczytem granicy. | FIXED `3e27170` |
| Średnia | `CollectionHistoryView.tsx:269` | Job, który padł, renderował się jako „nothing in this range to collect" — czyli awaria czytana jako twierdzenie o braku historii instrumentu. | FIXED `3e27170` |
| **Wysoka** | `design.md`, Migration Plan | Sekcja otwierała się zdaniem „bez migracji bazy", napisanym zanim `0007` powstała i nigdy potem nieprzejrzanym, mimo że migrację dołożyła grupa 5 tej samej zmiany. **To położyło produkcję** — patrz niżej. | FIXED `909d796` |

### Awaria wdrożeniowa, w całości

Po scaleniu #47 trzy deploye przeszły i zameldowały sukces, a produkcyjny `market-data`
stanął na nowym kodzie przy bazie na `0006`. Nowy kod czyta `history_ends_at` w każdym
odczycie pokrycia, więc `/candles`, `/coverage`, `/jobs/estimate` i `POST /pairs` zaczęły
odpowiadać pięćsetką naraz. Operator zobaczył „the archive failed to answer this request" —
tak wygląda `UndefinedColumnError` po przejściu przez catch-all w `app.py`.

Trzy rzeczy złożyły się na to i żadna sama by nie wystarczyła:

1. Plan wdrożenia twierdził, że migracji nie ma.
2. Migracja nie jedzie ani z obrazem (`Dockerfile`, decyzja 8.6), ani z workflow — robi ją
   operator, i nic mu o tym nie przypomina.
3. `deploy-market-data.yml` **zameldował sukces przy leżącej aplikacji**: smoke check na
   końcu uderza w endpoint, który nie dotyka pokrycia.

Naprawione ręcznym `alembic upgrade 0007` na produkcji. Punkt 3 zostaje otwarty i wróci
przy każdej następnej migracji — patrz Gaps.

## Spec coverage

### `capital-market-data`

| Requirement / Scenario | Proven by |
|---|---|
| **Odczyt historii mówi, który okres jeszcze trwa** | |
| Najnowsza świeca odczytu sięgającego teraźniejszości | `test_history.py::test_the_newest_candle_of_a_read_reaching_now_is_forming`, `::test_a_period_that_has_ended_is_not_forming` |
| Rozdzielczość, której granica zależy od sesji rynku | `test_history.py::test_a_daily_candle_is_forming_while_the_market_is_open`, `::test_the_adapter_asks_the_market_before_calling_a_daily_candle_settled` |
| Rynek zamknięty | `test_history.py::test_a_daily_candle_is_settled_once_the_market_shuts`, `::test_a_shut_market_settles_todays_daily_candle` |
| Odczyt zakotwiczony w przeszłości | `test_history.py::test_a_read_anchored_in_the_past_has_nothing_forming` |
| **Historia jest stronicowana poza limit providera** | |
| Prośba o więcej świec, niż mieści jedno żądanie | `test_history.py::test_a_multi_page_read_returns_one_ordered_series` |
| Historia instrumentu się kończy | `test_history.py::test_running_past_the_bottom_keeps_what_was_collected`, `::test_an_empty_window_after_a_full_one_still_ends_history` |
| Okno nie przynosi nic nowego | `test_history.py::test_a_window_with_no_progress_ends_the_loop` |
| Pierwsze okno odczytu nic nie przynosi | `test_history.py::test_an_empty_first_window_is_not_the_end_of_history`, `::test_an_empty_first_window_with_an_anchor_is_not_an_ending_either` |
| Odczyt ograniczony momentem, nie liczbą | `test_history.py::test_reaching_the_floor_stops_the_paging`, `::test_a_floor_drops_candles_older_than_it` |
| Okno przycięte do granicy konsumenta nic nie przynosi | `test_history.py::test_not_found_for_a_window_clamped_to_the_floor_is_not_an_ending`, `::test_no_progress_at_a_window_clamped_to_the_floor_is_not_an_ending` |
| Historia providera kończy się powyżej granicy konsumenta | `test_history.py::test_running_out_of_provider_data_above_the_floor_still_ends_history` |

### `capital-streaming`

| Requirement / Scenario | Proven by |
|---|---|
| **Świeca w budowie jest składana przez moduł** | |
| Pierwsze kwotowanie nowego okresu | `test_forming.py::test_a_quote_in_the_next_period_opens_a_new_candle` |
| Kwotowania wewnątrz okresu | `test_forming.py::test_later_quotes_stretch_the_range_and_move_the_close` |
| Przychodzi świeca od providera | `test_forming.py::test_a_sealed_candle_overwrites_what_was_assembled` |
| Rozdzielczość bez stałej granicy okresu | `test_forming.py::test_a_seeded_period_takes_quotes_without_any_arithmetic`, `::test_a_session_bound_resolution_never_guesses_a_boundary` |
| Pierwsze kwotowanie na rozdzielczości bez stałej granicy | `test_hub.py::test_a_daily_room_publishes_before_the_provider_seals_anything` |
| Okres się przetacza, zanim provider go zamknie | `test_forming.py::test_a_sealed_candle_is_never_stretched_into_the_next_period`, `test_hub.py::test_a_daily_room_asks_again_once_the_provider_seals_the_period` |
| Provider nie odpowiada na pytanie o granicę | `test_hub.py::test_a_provider_with_no_newer_period_leaves_the_room_silent`, `::test_a_boundary_read_that_raises_does_not_take_the_feed_with_it` |
| Subskrybent dołącza w środku okresu | `test_hub.py::test_a_late_joiner_is_handed_the_bar_already_forming`, `::test_a_late_joiner_is_not_handed_a_finished_period_as_forming` |

Poza scenariuszami, jako regresje po przeglądzie: `test_hub.py::test_a_reconnect_inside_the_same_period_keeps_publishing`,
`::test_a_provider_that_keeps_saying_no_is_not_asked_once_per_quote`,
`test_forming.py::test_a_break_and_a_seal_are_told_apart`.

### `market-data-jobs`

| Requirement / Scenario | Proven by |
|---|---|
| **Data OD jest przycinana do tego, co provider ma** | |
| Data sprzed historii providera | `test_jobs_runner.py::test_history_ended_bulk_skips_older_pending_chunks_of_the_same_pair` — przycięcie odkrywa dziś zlecenie, nie planowanie; **luka**, patrz Gaps |
| Data wcześniejsza niż granica zapamiętana przez archiwum | `test_jobs_plan.py::test_a_recorded_boundary_does_not_clip_a_deeper_request`, `test_app.py::test_asking_deeper_than_the_boundary_drops_it_and_plans_the_whole_range` |
| Wycena tej samej prośby | `test_jobs_plan.py::test_an_estimate_prices_what_the_job_will_do_and_writes_nothing`, `test_app.py::test_pricing_the_same_request_leaves_the_boundary_alone` |
| Data w przyszłości | `test_jobs_plan.py::test_a_future_request_is_refused` |

### `market-data-store`

| Requirement / Scenario | Proven by |
|---|---|
| **Zapisywana jest wyłącznie świeca zamknięta** | |
| Strumień niesie świecę w budowie | `test_store.py::test_a_forming_candle_is_refused`, `test_ingest.py` (ścieżka `live.py`) |
| Odczyt historii niesie okres, który jeszcze trwa | `test_ingest.py::test_a_fill_does_not_store_the_period_still_running`, `test_jobs_runner.py::test_a_chunk_does_not_store_the_period_still_running` |
| Okres się zamyka | `test_store.py::test_a_closed_candle_replaces_nothing_a_forming_one_left_behind` |
| **Archiwum wie, co pokrywa** | |
| Brak świecy wewnątrz pokrycia | `test_coverage.py::test_a_missing_candle_inside_coverage_means_the_market_was_shut` |
| Brak świecy poza pokryciem | `test_coverage.py::test_a_missing_candle_outside_coverage_means_nobody_looked` |
| Historia instrumentu się skończyła | `test_coverage.py::test_the_end_of_provider_history_is_remembered`, `::test_a_merge_does_not_drag_the_boundary_down_to_the_range_start`, `test_jobs_runner.py::test_history_ended_bulk_skips_older_pending_chunks_of_the_same_pair` |
| Odczyt kończy się bez ani jednej świecy | `test_coverage.py::test_a_boundary_must_say_where_it_lies`, `test_jobs_runner.py::test_a_chunk_that_brought_back_nothing_records_no_boundary` |
| Prośba o dane starsze niż zapisana granica | `test_coverage.py::test_a_deeper_request_drops_the_boundary_and_keeps_the_coverage`, `test_app.py::test_asking_deeper_than_the_boundary_drops_it_and_plans_the_whole_range` |
| Odczyt stanu pokrycia nie zmienia granicy | `test_app.py::test_pricing_the_same_request_leaves_the_boundary_alone`, `::test_re_adding_a_pair_without_a_date_leaves_the_boundary_alone` |

## Gaps

**Scenariusz „Data sprzed historii providera" nie ma testu na własnym poziomie.** Wymaganie
mówi, że zakres zostaje przycięty do najstarszego osiągalnego momentu i że zlecenie to
odnotowuje. Po tej zmianie przycięcia nie robi już planowanie — odkrywa je dopiero
działające zlecenie, przez `history_ended` i hurtowe pominięcie — a „odnotowanie" jest
wyliczane w terminalu z kawałków (`CollectionHistoryView.test.tsx::says how far back the
work actually got…`). Łańcuch jest pokryty w kawałkach, ale żaden test nie przechodzi go
end-to-end dla pary faktycznie płytszej niż prośba.

**`PairEstimate.clipped` nie jest już przez nic ustawiane.** Jedynym jego źródłem było
przycięcie do zapisanej granicy, a ono zniknęło: w chwili wyceny nikt nie wie, jak głęboko
sięga provider, i odpowiedź sprzed tygodnia nie jest odpowiedzią na dziś. Pole zostało
w kontrakcie, bo terminal je renderuje, a fakt, który nazywa, jest prawdziwy — tylko znany
dopiero po przebiegu zlecenia. Nie jest to przeoczenie i nie należy go „naprawiać"
przywracaniem przycięcia.

**`deploy-market-data.yml` nie ma bramki na niezaaplikowaną migrację.** Smoke check na
końcu uderza w endpoint, który nie dotyka pokrycia, więc deploy zameldował sukces przy
aplikacji odpowiadającej pięćsetką na cztery endpointy. To nie jest wada tej zmiany, ale
ta zmiana jest pierwszym przypadkiem, w którym zabolało, i wróci przy każdej następnej
migracji. Zasługuje na własną zmianę.

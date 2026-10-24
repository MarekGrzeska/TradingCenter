## Verdict

Etap 1 dostarczony: opcjonalny pakiet `strategies` pod `/strategies` z własną bazą (klucz 8130). Strategie są
dokumentami w języku formuł parsowanym przez `ast` i nigdy niewykonywanym, z niezmiennymi rewizjami. Silnik backtestu
decyduje na zamkniętej świecy i rozlicza wypełnienia na `MINUTE`. Uruchomienia są zadaniami w osobnym procesie na
każde uruchomienie. Raport nie ma werdyktu, a złote strategie pilnują wersji silnika. Zbudowany w ośmiu stosowanych PR
(#349–#356), każdy po przeglądzie i z poprawkami przed scaleniem.

Świadomie niekompletne: ekran, agent i narzędzia `/mcp` (etap 2), walidacja WF/MC/DSR (etap 3). **Strategia wymaga, żeby
archiwum zbierało `MINUTE` instrumentu handlowanego**: lokalna baza takich świec nie ma (najdrobniejsze jest `MINUTE_5`).
To jest wymaganie z design.md, a nie przeoczenie, ale przed pierwszym użyciem trzeba sprawdzić, które instrumenty
produkcja zbiera na `MINUTE`.

## Verified

- `modules/workbench`, 24.10.2026, gałąź `strategies/9-docs`: `uv run pytest -q -m "not db and not live"` — 1732 passed;
  `uv run pytest -q tests/strategies tests/test_roles.py tests/test_layering.py tests/test_database_server_mode.py`
  (z `-m db`, testcontainers) — 226 passed; `ruff check .` — All checks passed; `pyright` — 0 errors.
- `scripts`: `uv run pytest -q` — 211 passed, 27 skipped (w tym nowy `test_ensure_databases.py` i budżet puli).
- `uv run python -m strategies.openapi` — dokument się buduje, a reguła pól odpowiedzi `tc-runtime` przechodzi.
- `uv run python -m tests.strategies.golden.regenerate` po ostatnich poprawkach — `golden.json` bajt w bajt bez zmian.
- Pomiar (syntetyczny rok, 375 840 minut): strategia HOUR 0,1 s, strategia MINUTE ze stanem w wejściu 8 s, ~190 MB;
  losowe wejście ×100: 1,7 s (HOUR) i 27 s (MINUTE). Z tego domyślne limity: 1,5 mln minut i 600 s.
- `db-cost-check` (#353): odczyt zakresu w archiwum to `Bitmap Index Scan on candles_pkey` z `Index Cond`, 322 bufory
  na 13 642 wiersze; klasa C2, nigdy na zegarze.
- `STRATEGIES_DB_PASSWORD` ustawiony w środowisku `vps` 24.10.2026 21:13 UTC, przed merge do `main`.

## Findings

Każdy PR przeszedł `code-review` (medium albo high). Ważne znaleziska poprawiono przed scaleniem, a pełne listy są w
komentarzach PR.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysokie | `deploy/scripts/fill-github-environment.sh` | Edycja w trybie tekstowym zamieniła dosłowne CR w `tr -d` na znak nowej linii; id z `az` na Windows dostałyby `\r` | FIXED `2c722c42` |
| Wysokie | `evaluate.py`, `requirements.py`, `document.py` | Łańcuch `@` (`x @ US500 @ DAY`) czytał kontekst pośredni (traded, DAY), którego nikt nie pobiera → KeyError | FIXED `5092e13a` |
| Wysokie | `engine.py` | Zlecenie limit/stop z ceną NaN czekało w nieskończoność i blokowało wszystkie kolejne wejścia | FIXED `5092e13a` |
| Wysokie | `queue.py` | Start procesu `spawn` (przepychanie całego zadania przez potok) i parsowanie serii blokowały pętlę zdarzeń, którą dzieli strumień świec i rozmowa | FIXED `0741566a` |
| Wysokie | `queue.py`, `runs.py` | Jeden błąd połączenia kończył pętlę kolejki na zawsze; anulowane uruchomienie mogło zachować transakcje bez raportu | FIXED `0741566a` |
| Średnie | `document.py` | `schema` jako `2.0`/`"2"` omijał limit; `Infinity` przechodził walidację i wywracał zapis do jsonb | FIXED `837d1656` |
| Średnie | `formula.py` | Kolumny w bajtach UTF-8 i po `strip`; ogromna liczba dawała `OverflowError` zamiast problemu | FIXED `c59b6489` |
| Średnie | `reading.py` | Minuty instrumentu czytane z rozgrzewką (DAY ze średnią 200 → ~470 tys. nadmiarowych wierszy ponad limit) | FIXED `5092e13a` |
| Średnie | `reports.py`, `engine.py` | Losowe wejścia trafiające w otwartą pozycję przepadały; benchmark mógł zabrać wynik strategii przez limit czasu | FIXED `6545a35a` |
| Średnie | `reports.py` | Czas w pozycji liczony zegarem (weekend = 62 bary), krzywa kapitału bez narosłego finansowania, Sharpe z ujemnego kapitału | FIXED `6545a35a` |
| Średnie | `routers/runs.py` | Lista uruchomień bez stronicowania i z pełnymi raportami; liczby spoza zakresu kolumn dawały 500 | FIXED `d3d45e8f` |
| Niskie | `golden/regenerate.py` | Nowy przypadek traktowany jak zmieniony wynik, usunięty nie; porównanie dokładne zamiast z tolerancją | FIXED `b7208886` |
| Niskie | `reports.py` | Losowe wejście zawsze składa zlecenie rynkowe, także dla strategii wchodzącej limitem lub stopem | Świadomie: raport mówi `"entry": "market"` |
| Niskie | `queue.py` | Anulowanie jest zauważane między odczytem a startem procesu i w trakcie liczenia, ale nie między stronami archiwum | Świadomie: odczyt ograniczają limit świec i limit czasu |

## Spec coverage

Wszystkie testy są w `modules/workbench/tests/strategies/`, poza `tests/test_roles.py`.

| Requirement / Scenario | Proven by |
|---|---|
| **strategies-language** · Formuła jest parsowana, nigdy wykonywana · Formuła z dozwolonych konstrukcji | `test_language.py::test_a_formula_built_from_the_language_is_accepted` |
| · Konstrukcja spoza listy | `test_language.py::test_a_construction_outside_the_list_is_refused_with_its_place`; `::test_nothing_in_the_package_executes_code` |
| Serie, przesunięcia i okna · Przesunięcie wstecz | `test_engine.py::test_the_whole_axis_at_once_equals_the_axis_cut_at_each_bar` (przez `highest(high, 5)[1]`) |
| · Indeks ujemny | `test_language.py::test_an_offset_into_the_future_or_from_a_formula_is_refused` |
| Zamknięta lista funkcji, otwarta na katalog · Nowy wskaźnik w katalogu | `test_language.py::test_a_new_catalogue_entry_is_a_function_without_a_change_here` |
| · Wskaźnik wielolinijkowy bez wyboru linii | `test_language.py::test_a_multi_line_indicator_without_its_line_says_which_lines_there_are` |
| · Parametr wskaźnika poza zakresem katalogu | `test_language.py::test_an_indicator_parameter_outside_the_catalogue_range_names_the_range` |
| Inny interwał i inny instrument · Wyższy interwał w środku jego świecy | `test_alignment.py::test_a_higher_resolution_in_the_middle_of_its_bar_reads_the_one_that_closed` |
| · Rynek drugiego instrumentu zamknięty | `test_alignment.py::test_a_closed_market_reads_its_last_bar_and_says_it_is_stale` |
| Wartość widoczna od chwili dostępności · Seria publikowana z opóźnieniem | `test_alignment.py::test_a_value_published_late_is_not_seen_before_it_was_published` |
| Stan pozycji i historia · Stop z wartości na wejściu | `golden/` `crossover_with_costs` (`at_entry(atr(14))`); `test_engine.py::test_risk_fraction_sizes_from_the_distance_to_the_stop` |
| · Stan pozycji w warunku wejścia | `test_language.py::test_the_open_position_in_an_entry_condition_is_refused` |
| Typy i błędy · Literówka w nazwie funkcji | `test_language.py::test_a_misspelt_function_hears_the_nearest_name` |
| · Liczba w miejscu warunku | `test_language.py::test_a_number_where_a_condition_stands_is_a_type_error` |
| **strategies-documents** · Kształt · Dokument bez stopu | `test_documents.py::test_a_document_without_a_stop_is_refused_because_of_r` |
| · Nieznane pole | `test_documents.py::test_an_unknown_field_is_refused_not_dropped` |
| Sprawdzany przy zapisie · Symbol, którego archiwum nie zbiera | `test_documents.py::test_a_symbol_the_archive_does_not_collect_is_named` |
| · Cykl w zmiennych | `test_documents.py::test_a_cycle_in_lets_names_both` |
| Niezmienna rewizja · Edycja strategii | `test_store.py::test_an_edit_is_the_next_revision_and_the_previous_one_stays_as_it_was` |
| · Ponowny zapis tej samej treści | `test_store.py::test_saving_the_same_content_again_creates_nothing_and_answers_the_latest` |
| Wersja schematu · Dokument ze schematu przyszłego | `test_documents.py::test_a_document_from_a_future_schema_names_both_versions`; `::test_a_future_schema_written_as_a_float_or_text_is_still_refused` |
| · Dokument zapisany przy starszym schemacie | **luka** — istnieje jeden schemat (Gaps) |
| Archiwizacja · Archiwizacja | `test_store.py::test_an_archived_strategy_leaves_the_list_and_keeps_its_runs`; `test_api.py::test_a_strategy_is_saved_revised_read_and_archived` |
| **strategies-backtest** · Decyzja na zamkniętej świecy · Zlecenie rynkowe z sygnału | `test_engine.py::test_a_signal_on_the_close_fills_on_the_open_of_the_next_minute_with_the_spread` |
| Wynik nie zależy od danych po chwili decyzji · Dłuższy zakres | `test_engine.py::test_a_longer_range_leaves_the_trades_of_the_shorter_one_as_they_were`; `::test_the_whole_axis_at_once_equals_the_axis_cut_at_each_bar` |
| Strona ceny i spread · Stop pozycji krótkiej | `test_engine.py::test_a_short_stop_is_touched_by_the_ask_though_the_bid_never_reaches_it` |
| Zlecenia wejścia · Stop wejścia przeskoczony luką | `test_engine.py::test_a_stop_entry_jumped_by_a_gap_fills_at_the_open_beyond_it` |
| · Sygnał przy otwartej pozycji | `test_engine.py::test_a_signal_while_a_position_is_open_is_not_a_second_one` |
| Wyjścia i limity · Trailing tylko zacieśnia | `test_engine.py::test_a_trailing_stop_only_ever_tightens` |
| · Stop dnia | `test_engine.py::test_after_the_daily_stop_nothing_is_entered_until_midnight_utc` |
| Niejasna minuta · Stop i cel w jednej minucie | `test_engine.py::test_a_minute_spanning_both_stop_and_target_closes_on_the_stop_and_says_it_assumed` |
| Rozmiar pozycji · Ułamek ryzyka | `test_engine.py::test_risk_fraction_sizes_from_the_distance_to_the_stop` |
| Model kosztów · Brak modelu kosztów | `test_engine.py::test_a_cost_model_has_no_defaults`; `test_runs.py::test_a_run_without_costs_is_not_a_request` |
| · Pozycja przez weekend | `test_engine.py::test_a_long_held_from_friday_evening_to_monday_morning_pays_three_nights`; `::test_financing_is_booked_on_the_trade` |
| Zadanie w tle z limitami · Restart w trakcie | `test_runs.py::test_a_run_left_running_by_a_previous_process_is_marked_interrupted` |
| · Za długi zakres | `test_runs.py::test_a_range_past_the_ceiling_is_refused_with_both_numbers` |
| (limit czasu, anulowanie) | `test_runs.py::test_a_run_past_its_time_limit_is_stopped_and_says_why`; `::test_a_running_run_is_stopped_by_the_queue_when_cancelled_and_the_process_answers_meanwhile` |
| Ten sam wkład, ten sam wynik · Złota strategia | `test_golden.py::test_a_golden_strategy_gives_its_recorded_result`; `::test_the_recording_is_of_this_engine_version`; `::test_the_regenerator_refuses_a_moved_or_vanished_result_and_accepts_an_addition_or_a_new_version` |
| **strategies-reports** · Bez werdyktu · Strategia z ujemnym wynikiem | `test_reports.py::test_a_report_carries_numbers_and_no_verdict` |
| Metryki · Brak transakcji | `test_reports.py::test_without_trades_every_trade_metric_is_empty_not_zero`; `::test_a_strategy_that_never_enters_says_so` |
| · Brak strat | `test_reports.py::test_without_a_loss_the_profit_factor_is_empty` |
| Każda transakcja widoczna · Transakcja zamknięta trailingiem | `test_engine.py::test_a_trailing_stop_only_ever_tightens` (`exit_reason == "trail"`) |
| Dwa punkty odniesienia · Powtórzenie z tym samym ziarnem | `test_reports.py::test_the_random_entry_benchmark_repeats_exactly_with_the_same_seed` |
| Raport mówi, z czego powstał · Dane zmieniły się | `test_alignment.py::test_two_reads_of_a_series_that_changed_have_different_fingerprints`; `test_runs.py::test_a_queued_run_is_computed_in_a_worker_and_leaves_its_trades_and_provenance` |
| Uruchomienia trwałe i policzone · Kolejne uruchomienie | `test_store.py::test_an_archived_strategy_leaves_the_list_and_keeps_its_runs` (`trials == 1`) |
| **strategies-api** · Kontrakt REST · Zakolejkowanie uruchomienia | `test_runs.py::test_post_runs_queues_at_once_and_a_missing_strategy_is_a_404`; `test_api.py::test_the_caller_record_names_exactly_the_routes_the_package_serves` |
| Opis języka z tego samego źródła · Nowy wskaźnik w katalogu | `test_api.py::test_the_language_lists_the_registry_and_the_catalogue` |
| Walidacja bez zapisu · Dokument z błędami | `test_api.py::test_validate_answers_what_saving_would_and_writes_nothing` |
| Dostęp ma operator · Oglądający czyta listę strategii | `tests/test_roles.py::test_a_viewer_reaches_the_two_archives_for_reading_and_no_other_door` (`/strategies/strategies`, `/strategies/runs`) |
| Brak drogi do rachunku · Przegląd zależności pakietu | `test_api.py::test_the_package_has_no_road_to_an_account` |
| **workbench-process** · Obecny z konfiguracji · Baza nieskonfigurowana | `test_package.py::test_without_a_database_the_package_is_not_part_of_the_process`; `::test_a_line_left_blank_is_the_line_not_being_there` |
| · Baza skonfigurowana, ale nieosiągalna | `test_package.py::test_a_configured_database_that_does_not_answer_stops_the_start_and_names_it` |
| · Backtest w toku | `test_runs.py::test_a_running_run_is_stopped_by_the_queue_when_cancelled_and_the_process_answers_meanwhile` — tylko połowa (Gaps) |

## Gaps

- **„Dokument zapisany przy starszym schemacie”**: istnieje jeden schemat (1), więc nie ma starszego do uruchomienia.
  Wymaganie zaczyna mieć test w dniu pierwszego podniesienia `SCHEMA_VERSION`.
- **„Backtest w toku”** jest sprawdzony na `/ping` pakietu strategii w tym samym procesie, a nie na `/market` ani na
  rozmowie w pełnym workbenchu. Liczenie idzie w osobnym procesie, a parsowanie i start procesu poza pętlą, więc
  mechanizm jest ten sam. Pełnego procesu z archiwum i rozmową test jednak nie stawia.
- **Minuty w archiwum**: patrz Verdict. Bez `MINUTE` dla instrumentu walidator odmawia z podpowiedzią, więc to stan
  działający, ale do sprawdzenia przed pierwszym użyciem.
- Po wdrożeniu (zadanie 9.3): `deploy-watch`, instalacja `backup.sh`/`backup-check.sh` z `strategies` na serwerze i
  pierwszy nocny zrzut — wynik dopisuje się tu albo w PR do `main`.

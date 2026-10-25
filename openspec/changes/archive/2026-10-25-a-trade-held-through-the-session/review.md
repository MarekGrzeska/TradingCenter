## Verdict

Strategia operatora z 25.10.2026 przechodzi walidację bez zmiany swoich reguł. Testy uruchamiają ją jako złotą strategię
na danych przechodzących przez zmianę czasu w USA 8 marca: wejście o 9:35, wyjście o 15:55 czasu nowojorskiego, bez R,
z depozytem 5%. Świadomie nie zrobiono dwóch rzeczy. Kalendarz świąt giełdowych to osobna zmiana. Próg zamknięcia przez
brokera nie jest modelowany: silnik zamyka pozycję przy zerze (D6), więc wynik blisko tej granicy jest optymistyczny.
Zadanie 7.3 (wdrożenie i pierwszy backtest na produkcji) czeka na merge.

## Verified

Uruchomione 25.10.2026 na gałęzi `feat/a-trade-held-through-the-session`:

- `modules/workbench`: `uv run ruff check .` — All checks passed; `uv run pyright` — 0 errors; `uv run pytest -q` — 3299
  passed, 11 skipped (z Dockerem, więc testy `-m db` też przeszły).
- `modules/terminal`: `tsc -b --noEmit` i `eslint .` bez uwag; `vitest run` — 1004 passed (89 plików) po poprawkach z
  review; `node scripts/contract.mjs check` — „Every contract is up to date”.
- `uv run python -m tests.strategies.golden.regenerate` — sześć złotych strategii nagranych pod `ENGINE_VERSION` 3. Po
  poprawce MAE nagranie odtworzono od wersji 2 z `main`, bo wersja 3 nie była jeszcze wydana.
- Na demo: brama uruchomiona na chwilę i `GET /instruments/{symbol}/terms` — US100, US500 i GOLD mają depozyt 5
  `PERCENTAGE`, EURUSD 3,333333 (design D5).
- `openspec validate a-trade-held-through-the-session --strict` — valid.

## Findings

Z przeglądu `/code-review high` całej gałęzi, zweryfikowane w kodzie.

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `terminal/src/strategies/strategiesApi.ts` `mapHeadline`, `RunsPanel.tsx` | Lista uruchomień gubiła `return_pct`. Uruchomienie bez stopu nie miało tam żadnego wyniku, tylko kreski. | FIXED: `returnPct` w `Headline`, kolumna „Zwrot” |
| Średnia | `workbench/strategies/engine.py` `_minute` | MAE pomijała minutę, w której pozycja wychodzi na celu, choć jej niekorzystne ekstremum mogło być przed celem. Raport zaniżał najgłębszą stratę. | FIXED: ekstremum liczone przed rozstrzygnięciem celu; test `test_the_minute_a_trade_reaches_its_target_counts_toward_its_deepest_loss` |
| Średnia | `workbench/strategies/compare.py` | Porównanie przyjmowało uruchomienia liczone z różnym depozytem. Wielkości pozycji różniły się wtedy np. dwukrotnie, a nic tego nie mówiło. | FIXED: odmowa nazywa oba depozyty; delty `strategies-tools` i `strategies-api` |
| Średnia | `terminal/src/strategies/completions.ts` | Edytor nie podpowiadał `NEW_YORK`/`LONDON`/`TOKYO`, czyli jedynych argumentów funkcji sesji. | FIXED: podpowiedzi z `language.sessions`; `completions.test.ts` |
| Niska | `workbench/strategies/summary.py` `_reads_a_session` | Pomijało `exits.trail.distance`, przez co znikała uwaga „bez świąt giełdowych”. | FIXED |
| Niska | `workbench/strategies/engine.py` | Komentarz `ENGINE_VERSION` miał cztery linie historii, wbrew sufitowi z CLAUDE.md. `_capital_floor` miał nieużywany parametr. | FIXED. Podwójne `book.broke = True` zostaje: na progu kapitał jest zerem tylko z dokładnością do zaokrąglenia (komentarz w kodzie). |
| Niska | `workbench/strategies/evaluate.py` `_session` | Tabela dni sesji była budowana osobno dla każdej funkcji sesji na tej samej osi. | FIXED: pamięć podręczna `(sesja, kontekst)` w `Evaluator` |
| Niska | `workbench/strategies/document.py` `_session_axes` | Trzecia kopia przejścia drzewa przez łańcuchy `@`, obok `contexts()` i `requirements.needs`. | Zostaje: wspólne przejście to refaktor trzech miejsc, poza zakresem tej zmiany |
| Niska | `workbench/strategies/routers/runs.py`, `tools/running.py` | Profil kosztów pobrany od brokera zostaje zapisany, nawet gdy potem odmowa dotyczy depozytu. | Zostaje: profil i tak jest trzymany od pierwszego odczytu (D2 `costs-come-from-the-broker`), a „nothing was queued” mówi prawdę o uruchomieniu |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| language: Zamknięta lista funkcji — trzy scenariusze katalogu | bez zmian: `test_language.py::test_a_new_catalogue_entry_is_a_function_without_a_change_here`, `…multi_line_indicator…`, `…indicator_parameter_outside…` |
| language: Pierwsza świeca M5 sesji nowojorskiej | `test_sessions.py::test_the_first_m5_bar_of_new_york_is_one_and_the_next_two` |
| language: Europa zmienia czas przed USA | `test_sessions.py::test_new_york_opens_an_hour_earlier_in_poland_while_europe_has_changed_time_and_the_us_has_not` |
| language: Brak świecy otwarcia | `test_sessions.py::test_a_missing_opening_bar_does_not_renumber_the_day` |
| language: Minuty do zamknięcia | `test_sessions.py::test_minutes_to_the_close_are_counted_from_the_decision_and_turn_negative_after_it` |
| language: Funkcja sesji na osi dziennej | `test_documents.py::test_a_session_function_on_a_daily_axis_is_refused` |
| language: Nazwa sesji poza funkcją sesji | `test_language.py::test_a_session_stands_only_as_the_argument_of_a_session_function` |
| language: Te same godziny co na wykresie | `tests/test_session_hours_agree.py::test_a_session_of_the_language_is_the_session_the_chart_draws` |
| documents: Dokument bez stopu | `test_documents.py::test_a_document_without_a_stop_and_without_an_exit_is_refused` |
| documents: Nieznane pole | `test_documents.py::test_an_unknown_field_is_refused_not_dropped` |
| documents: Strategia sesyjna bez stopu | `test_documents.py::test_a_session_strategy_without_a_stop_is_accepted` |
| documents: Ułamek ryzyka bez stopu | `test_documents.py::test_without_a_stop_nothing_measured_in_r_is_accepted` |
| backtest: Trailing tylko zacieśnia · Stop dnia | `test_engine.py::test_a_trailing_stop_only_ever_tightens`, `…after_the_daily_stop_nothing_is_entered_until_midnight_utc` |
| backtest: Wyjście pięć minut przed końcem sesji | `test_engine.py::test_a_position_without_a_stop_leaves_five_minutes_before_new_york_closes` |
| backtest: Ułamek ryzyka | `test_engine.py::test_risk_fraction_sizes_from_the_distance_to_the_stop` |
| backtest: Ułamek depozytu · Ułamek wartości pozycji | `test_engine.py::test_a_deposit_or_a_value_as_a_fraction_of_equity_sizes_the_position` |
| backtest: Wynik transakcji bez stopu | `test_engine.py::test_a_result_without_a_stop_is_in_percent_of_the_equity_at_entry_and_not_in_r` |
| backtest: Long bez stopu traci cały kapitał | `test_engine.py::test_a_position_that_loses_the_whole_capital_is_closed_and_nothing_opens_after` |
| backtest: Pierwsze uruchomienie z ułamkiem depozytu | `test_broker_costs.py::test_the_first_run_sized_by_the_deposit_reads_it_and_leaves_the_cost_profile_alone` |
| backtest: Depozyt w nieznanej jednostce | `test_broker_costs.py::test_a_deposit_in_an_unknown_unit_refuses_the_run_and_keeps_nothing`, `…deposit_in_percent_becomes_a_fraction…` |
| backtest: Strategia bez ułamka depozytu | `test_broker_costs.py::test_a_run_not_sized_by_the_deposit_never_reads_it` |
| reports: Brak transakcji · Brak strat | `test_reports.py::test_without_trades_every_trade_metric_is_empty_not_zero`, `…without_a_loss_the_profit_factor_is_empty` |
| reports: Strategia bez stopu | `test_reports.py::test_a_strategy_without_a_stop_reports_nothing_in_r_and_everything_else` |
| reports: Transakcja zamknięta trailingiem | `test_engine.py::test_a_trailing_stop_only_ever_tightens` (`exit_reason == "trail"`) |
| reports: Najgłębsza strata otwarta | `test_reports.py::test_a_trade_carries_its_deepest_open_loss_and_its_result_in_percent` |
| reports: Powtórzenie z tym samym ziarnem | `test_reports.py::test_the_random_entry_benchmark_repeats_exactly_with_the_same_seed` |
| reports: Losowe wejście strategii bez stopu | `test_reports.py::test_a_strategy_without_a_stop_reports_nothing_in_r_and_everything_else` |
| reports: Dane zmieniły się między uruchomieniami | `test_alignment.py::test_two_reads_of_a_series_that_changed_have_different_fingerprints` |
| reports: Raport strategii z ułamkiem depozytu | `test_reports.py::test_a_report_sized_by_the_deposit_says_which_deposit` |
| tools: Różne koszty · Porównywalne · Różny depozyt | `test_tools.py::test_runs_with_different_costs_are_not_compared_and_the_difference_is_named`, `…comparable_runs_stand_side_by_side…`, `…runs_sized_by_different_deposits_are_not_compared` |
| api: Porównanie przez REST — trzy scenariusze | `test_api.py::test_runs_are_compared_on_the_wire_or_refused_with_the_difference_named` |
| terminal: Transakcja bez stopu | `RunForm.test.tsx` „is drawn without a stop line and reads its result in percent, not in R” |
| terminal: Wybór transakcji · Raport bez transakcji | e2e `backtests.spec.ts` BT-05, BT-06 |
| terminal: Uruchomienie sprzed krzywej kapitału | brak testu — luka sprzed tej zmiany |

## Gaps

- Terminal: „Uruchomienie sprzed krzywej kapitału” nie ma testu. To luka z poprzedniej zmiany: scenariusz tylko przepisano
  do delty.
- Testu odmowy depozytu przez REST z kodem 503 (archiwum nie odpowiada) nie ma. Ta sama ścieżka dla kosztów ma test
  (`test_a_broker_that_does_not_answer_leaves_the_profile_as_it_was`).
- 7.3: na produkcji agent zapisuje strategię operatora i uruchamia ją na US100 — po merge.

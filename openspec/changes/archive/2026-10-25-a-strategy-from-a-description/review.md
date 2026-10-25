## Verdict

Etap 2 dostarczony na gałęzi `strategies/stage-2-screen-and-agent`, jeszcze bez commita i bez wdrożenia. Pakiet
`strategies` dostał osiem narzędzi rozmowy. Są wołane jako funkcje, trafiają tylko do rozmowy i nie są montowane pod
`/mcp`. Do tego doszły:
- deterministyczne streszczenie po polsku;
- różnice między rewizjami po ścieżkach;
- zapis z rewizją bazową (409);
- profile kosztów instrumentów;
- `requested_by` i kolumna `headline` przy uruchomieniach;
- typowany `ReportOut` z dzienną krzywą (`ENGINE_VERSION` 2).

Terminal ma zakładkę Strategies, ładowaną leniwie i z edytorem CodeMirror 6. Panel agenta wysyła w turze otwartą
strategię i niezapisany tekst edytora. Zadanie 5.3, czyli wdrożenie i profile kosztów na produkcji, czeka na merge.

## Verified

- `modules/workbench`, 25.10.2026:
  - `uv run pytest -q tests/strategies` (z `-m db`, testcontainers): 182 passed;
  - pełny `uv run pytest -q`: 3209 passed, 11 skipped (przed dodaniem kolumny `headline`, po niej ponownie `tests/strategies`: 182 passed);
  - `ruff check .`: All checks passed;
  - `pyright strategies agent`: 0 errors.
- `modules/terminal`:
  - `tsc -b --noEmit`: czysto;
  - `eslint .`: czysto;
  - `vitest run`: 86 plików, 986 testów, wszystkie zielone;
  - `vite build`: osobny chunk `StrategiesView` (404 kB, gzip 133 kB) poza `index`.
- `modules/pocket`: `tsc -b --noEmit` czysto po regeneracji kontraktu agenta.
- Kontrakty: `node scripts/contract.mjs generate` w terminalu i pocket. Nowy `contract.strategies.generated.ts`,
  regenerowany `contract.agent.generated.ts` (+20 linii, `StrategyInViewIn`). Potem `contract.mjs check` w obu: exit 0.
- Złote strategie: `regenerate` pod wersją 2. Skrypt porównał stare i nowe nagranie przypadek po przypadku. Poza
  nowym polem `equity` raporty i transakcje są identyczne we wszystkich pięciu przypadkach.
- `db-cost-check`, syntetycznie w kontenerze dev: 5000 uruchomień z krzywą 3650 punktów, 50 strategii po 20 rewizji.
  - Lista uruchomień strategii z kolumną `headline` (odpytywana co 3 s tylko wtedy, gdy coś czeka): `Bitmap Index Scan
    on runs_by_strategy`, 111 buforów, 0,5 ms. Klasa C1.
  - Gdyby headline czytać z raportu, każde odpytanie rozpakowywałoby z TOAST całą krzywą. Dlatego powstała kolumna.
  - Lista strategii (LATERAL po ostatniej rewizji i licznik prób): 4,3 ms, 5235 buforów przy 5000 uruchomieniach. Klasa
    C2, czytana tylko po turze, kliknięciu albo wejściu na zakładkę.
  - Walidacja na żywo nie dotyka bazy. Katalog to pliki, a lista par ma pamięć 60 s.
- Powierzchnia narzędzi: 8 827 znaków, sufit 10 000 (`test_tools.py`). Rozmowa płaci za to w każdej turze, także
  niezwiązanej ze strategiami.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Średnie | `strategies/runs.py` (lista) | Pierwsza wersja czytała metryki headline z `report->…`, więc odpytywanie listy co 3 s rozpakowywało krzywą każdego uruchomienia | FIXED przed commitem: kolumna `headline` w migracji 0002 |
| Średnie | `terminal/src/data/http.ts` | Odmowa z `detail` jako tekstem gubiła resztę ciała (`problems`, `latest_revision`), więc edytor nie miałby czego zaznaczyć, a 409 nie dałoby się odróżnić | FIXED: `problem` niesie całe ciało |
| Niskie | `terminal/src/chart/Chart.tsx` | Znaczniki trzymają się serii z chwili utworzenia; po ponownym utworzeniu instancji wykresu (StrictMode) znikną do następnej zmiany listy | Świadomie: tylko dev, a nowa strona transakcji odtwarza znaczniki |
| Niskie | `ReportPanel.tsx` | Znacznik pada na początek świecy liczony zegarem; dla `DAY`/`WEEK` sesja archiwum może zaczynać się inaczej i znacznik nie trafi w świecę | Otwarte |
| Niskie | `StrategiesView.tsx` | Szkic nowej strategii z niezapisanymi zmianami zostaje zastąpiony strategią, którą agent utworzył w turze | Świadomie: o to operator prosi agenta |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **strategies-tools** · Powierzchnia · Pakiet nieobecny | `workbench/app.py` buduje `strategies_tools` tylko przy zamontowanym pakiecie; bez testu procesu — luka |
| · Nowy wskaźnik w katalogu | `strategy_language` woła `language.describe`, jak `GET /language`: `tests/strategies/test_api.py::test_the_language_lists_the_registry_and_the_catalogue`; przez narzędzie — luka |
| Tylko rozmowa · Narzędzia dla agenta zespołu | luka (tylko kod `workbench/app.py`); `/mcp`: `test_tools.py::test_the_tools_are_not_served_over_the_network` |
| Autor `agent` · Zmiana stopu · Operator zapisał w międzyczasie | `test_tools.py::test_the_agent_saves_a_revision_as_itself_with_its_changes_and_is_refused_on_a_stale_base` |
| Agent nie podaje kosztów · Instrument bez profilu | `test_tools.py::test_without_a_cost_profile_the_agent_cannot_run_and_nothing_is_queued`; brak narzędzia kosztów: `::test_the_surface_is_the_eight_tools_and_none_sets_costs` |
| Uruchomienie z rozmowy · Krótkie · Druga prośba | `test_tools.py::test_a_short_run_answers_within_the_wait_counts_as_a_trial_and_a_second_waits_its_turn` |
| · Długie uruchomienie | luka (ścieżka po upływie `WAIT_SECONDS` bez testu) |
| Porównanie · Różne koszty · Porównywalne | `test_tools.py::test_runs_with_different_costs_are_not_compared_and_the_difference_is_named`, `::test_comparable_runs_stand_side_by_side_without_a_verdict` |
| Opisy prowadzą autora · Opis bez godzin sesji | `test_tools.py::test_the_descriptions_tell_the_model_how_to_write_and_when_to_run` |
| **strategies-documents** · Streszczenie · Filtr na innym interwale | `test_summary.py::test_another_interval_is_named_the_way_the_terminal_names_it` |
| · Godzina w limicie | `test_summary.py::test_an_hour_of_the_language_is_utc_with_the_hours_in_poland` |
| · Ten sam dokument dwa razy | `test_summary.py::test_the_same_document_is_always_the_same_summary`; sformułowania: `::test_every_name_and_function_of_the_language_has_a_phrase` |
| Różnice · Zmiana stopu · Pierwsza rewizja | `test_changes.py::test_a_changed_stop_is_one_change_at_its_path`; `test_api.py::test_revisions_are_listed_compared_and_a_stale_base_is_a_conflict` |
| Rewizja bazowa · Nieaktualna podstawa | `test_store.py::test_a_save_based_on_a_revision_no_longer_the_latest_is_a_conflict_and_saves_nothing` |
| **strategies-backtest** · Profil · Zmiana po uruchomieniu | wartości kopiowane do `request`: `test_tools.py::test_a_short_run_…` (`row.request["costs"]`); zmiana profilu po uruchomieniu — luka |
| · Niepełny profil spreadu | `test_api.py::test_a_cost_profile_is_set_replaced_read_and_refused_when_malformed` |
| Kto poprosił · Uruchomienie z rozmowy | `test_tools.py::test_a_short_run_…` (`requested_by == "agent"`, `trials == 1`) |
| **strategies-reports** · Krzywa zgodna z obsunięciem | `test_reports.py::test_the_curve_in_the_report_is_the_one_its_drawdown_was_measured_on` |
| **strategies-api** · Lista z metrykami · Konflikt zapisu | `test_api.py::test_runs_are_listed_read_and_paged_and_a_missing_one_is_a_404`, `::test_revisions_are_listed_compared_and_a_stale_base_is_a_conflict` |
| Raport w kontrakcie · Pole się zmienia | `test_reports.py::test_every_field_a_report_carries_has_its_place_in_the_contract` i `contract:check` |
| **agent-chat** · Otwarta strategia (trzy scenariusze i sufit) | `tests/agent/test_sessions_router.py::test_a_turn_carrying_the_open_strategy_hands_it_and_its_draft_to_the_model` |
| **agent-tools** · Zapis strategii · Koszty poza zasięgiem | narzędzia: `test_tools.py`; scenariusze modelowe — bez testu (zachowanie modelu) |
| **terminal-shell** · Interwał w dokumencie strategii | lista: `StrategiesView.test.tsx` („h4”, nie „HOUR_4”); podpowiedź `h4` obok `HOUR_4`: `completions.ts` bez testu — luka |
| **terminal-strategies** · Pakiet nieobecny | `StrategiesView.test.tsx` „names the setting…” |
| Edytor · Literówka | `jsonPaths.test.ts` (kolumna przez ucieczki JSON); w żywym edytorze — luka |
| · Zapis, gdy agent zapisał | mapowanie 409: `strategiesApi.test.ts`; decyzja: `followTurn.test.ts`; w widoku — luka |
| Streszczenie obok · Zmiana stopu · Tekst z błędem | luka (widok bez testu) |
| Historia · Rewizja agenta · Przywrócenie | luka (widok bez testu; przywrócenie to zwykły zapis z podstawą) |
| Współpraca z panelem · Agent poprawia · Niezapisane zmiany · Nowa strategia | `StrategiesView.test.tsx` „takes the agent's revision…”; `followTurn.test.ts`; wysyłka: `agentApi.test.ts` „sends the strategy open…” |
| Formularz · Zakres ponad sufit · Bez profilu | luka |
| Lista uruchomień · Uruchomienie się kończy | luka (`anyPending` bez testu) |
| Raport · Wybór transakcji · Bez transakcji · Sprzed krzywej | krzywa: `curve.test.ts`; reszta — luka |

## Gaps

- Teams i katalog alertów bez narzędzi strategii: sprawdzone tylko lekturą `workbench/app.py`. Test potrzebowałby
  procesu uruchomionego z `STRATEGIES_DATABASE_URL` w chwili importu `workbench.app`.
- Widoki zakładki poza trzema testami CRUD: formularz, historia, raport, streszczenie przy błędzie, zaznaczenie w żywym
  edytorze CodeMirror.
- Nie oglądałem zakładki w przeglądarce na żywym stosie. Lokalna baza nie ma serii `MINUTE` (review etapu 1), więc
  backtestu i tak nie da się tam uruchomić.
- 5.3 po merge: `deploy-watch`, a potem profile kosztów dla instrumentów zbieranych na `MINUTE`.

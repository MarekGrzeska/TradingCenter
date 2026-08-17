## Verdict

Zegar, wyzwalacze i bezpieczniki pracy bez nadzoru są kompletne i przetestowane przeciw
prawdziwemu PostgreSQL-owi oraz prawdziwemu serwerowi MCP. Przejęcie wyzwolenia
warunkowym `UPDATE`, zwijanie pominiętych slotów do jednego, zbocze `false → true`,
trzeci stan „nie wiadomo" i samoczynne wyłączenie po serii niepowodzeń — każde z tych
zachowań ma test, który je wymusza, a nie tylko odwiedza.

Review znalazło **dwa błędy z realnym skutkiem na produkcji i jeden ślepy bezpiecznik**,
wszystkie na szwie z fazą 2, która scaliła się po tej gałęzi. Najpoważniejszy:
`check_unattended` pytał ręcznie prowadzoną listę nazw, która przez całą fazę 2 była
pusta — czyli kontrola wymagana przez `specs/teams-schedules` chodziła, przechodziła
testy i nie łapała `place_order`, mimo że `trading-mcp` ogłasza je jako zapis. Wszystkie
trzy naprawione w tym przebiegu, z testami, które nie przejdą po cofnięciu poprawki.

Czego tu nie ma i **nie jest przeoczeniem**: przebiegu od końca do końca na uruchomionym
stosie (zadanie 8.2, odhaczone jako świadoma decyzja operatora — testy `-m db` pokrywają
te same trzy sytuacje, ale nie pokrywają zegara budzącego się samego w App Service). To
jedyny powód, dla którego `SCHEDULER_ENABLED` zostaje `false`; wcześniejszy powód —
ślepy bezpiecznik — właśnie zniknął.

## Verified

Uruchomione, z wynikiem:

| Komenda | Wynik |
|---|---|
| `uv run pytest` (teams) | `345 passed` (przed poprawkami 337) |
| `uv run pytest -m db` (teams) | `165 passed, 180 deselected` — prawdziwy PostgreSQL w kontenerze jednorazowym |
| `uv run ruff check .` (teams) | `All checks passed!` |
| `uv run pyright` (teams) | `0 errors, 0 warnings` |
| `vitest run` (terminal) | `56 files, 854 passed` (przed poprawkami 853) |
| `eslint .` (terminal) | czysto |
| `tsc -b --noEmit` (terminal) | `exit=0` |
| `node scripts/contract.mjs check` | `Every contract is up to date.` |
| `terraform fmt -check -recursive` · `validate` | czysto · `Success! The configuration is valid.` |

Zmiana kontraktu: **żadna**. `teams/contract.py` nie został tknięty przez to review, więc
`contract.generated.*` po stronie terminala jest bajt w bajt ten sam.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Wysoka** | `teams/validation.py:135` (`STATE_CHANGING_TOOLS`) | Bezpiecznik wymagany przez `specs/teams-schedules` („Harmonogram nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia") pytał ręcznie prowadzony `frozenset()` nazw — pusty od dnia, w którym powstał. Faza 2 dołożyła `trading-mcp` z `place_order` i `readOnlyHint: false`, i nie dopisała nic do tej listy, bo nic jej o niej nie mówiło. Skutek: harmonogram nad zespołem składającym zlecenia był przyjmowany **bez** potwierdzenia, a jedyne testy tej ścieżki podawały zbiór ręcznie, więc świeciły na zielono nad martwą kontrolą. | FIXED — sprawdzenie odwrócone na zbiór *pozytywny*: `AnnouncedSnapshot.read_only` (nazwy, które każdy ogłaszający serwer podał jako `readOnlyHint: true`), a wszystko poza nim wymaga `unattended_ack`. Zapis ogłoszony jako zapis, narzędzie bez adnotacji i narzędzie z serwera, którego nie dało się zapytać, to trzy powody niepewności i jedna odmowa — to ostatnie zamyka wariant „serwer był chwilowo padnięty przy zapisie, więc harmonogram przeszedł, a zlecenia zaczęły lecieć, gdy wrócił". 4 nowe testy trasowe (przeciw stand-inowi naprawdę ogłaszającemu `place_order`) + 5 jednostkowych |
| **Wysoka** | `teams/scheduler/clock.py:195` (`_start_from`) | Łapało `(DefinitionRefused, DailyCostLimitReached)`. Faza 2 dołożyła do `start_run_on_revision` **drugi** dobowy sufit, `DailyOrderLimitReached` — i ten leciał przez `_fire_schedule` wprost do `Clock.tick()`. Skutki dwa, oba ciche: wyzwolenie nie zostawiało wiersza w `schedule_fires` (wbrew „Wyzwolenie bez przebiegu zostawia zapisany powód"), a `_run_forever` łapał wyjątek dopiero na poziomie całej pobudki — czyli **każdy kolejny harmonogram i wyzwalacz w tej pobudce był pomijany**, u wszystkich operatorów. | FIXED — łapane po klasach bazowych (`CostLimitReached`, `TradeLimitReached`), nie po dwóch konkretnych. Trasa może wyliczać (nieobsłużony sufit to jedno 500 dla patrzącego operatora), zegar nie. Test: `test_the_daily_order_limit_stops_a_schedule_and_leaves_a_row_rather_than_a_traceback` |
| Średnia | `teams/scheduler/clock.py:106` (`Clock.tick`) | Jedna pobudka przechodzi harmonogramy wszystkich operatorów w pętli, bez izolacji. Dowolny wyjątek z jednego wiersza (zerwane połączenie, uszkodzony `arguments`) zabierał ze sobą resztę listy — i to bezgłośnie, bo wiersz, który padł, nie dochodził też do `record_fire`. Powyższy błąd był tego pierwszym objawem, ale przyczyna jest osobna i przeżyłaby jego naprawę. | FIXED — `Clock._attempt` zamyka każdy wiersz we własnym `try`, z logiem nazywającym, który to był. Zewnętrzna sieć w `_run_forever` zostaje, ale znaczy teraz węziej: awarię samej pobudki (dwa `SELECT`-y), nie jednego wiersza. Test: `test_one_schedule_failing_does_not_silence_the_others_in_the_same_wake` |
| Niska | `teams/scheduler/clock.py:352` (`_evaluate_condition`) | Powód zapisywany do historii przy braku serwera narzędzi mówił „MARKET_MCP_URL is unset" — nieprawda od fazy 2, w której serwery są dwa i wyzwalacz może stać na narzędziu z `trading-mcp`. Operator czytający historię był kierowany do złego ustawienia. | FIXED — komunikat nazywa oba ustawienia |
| Niska | `terminal/src/teams/SchedulesPanel.tsx:224` (`EnableToggle`) | `api.enableSchedule(...).then(onChanged)` bez `catch`: odmowa modułu nie pokazywała się nigdzie, przycisk wracał do poprzedniego napisu, a odrzucona obietnica szła do konsoli. To jedyna kontrolka w tym panelu zmieniająca coś bez formularza wokół, więc `terminal-teams-schedules` („Odmowa modułu jest pokazana słowami modułu") nie był tu spełniony. | FIXED — własny stan błędu, ta sama ścieżka `refusalMessage` co przy zapisie. Test: `shows the module's own words when enabling is refused` |
| Niska | `tests/mcp_stand_in.py` | Stand-in nie zakładał adnotacji na narzędziach odczytu, choć `market-mcp` zakłada je na wszystkich (`READ_ONLY` w jego `_shared.py`). Po odwróceniu sprawdzenia byłby to katalog, którego nic w produkcji nie przypomina. | FIXED — `read_indicators` i `list_tracked_pairs` dostały `READ_ONLY`; `get_last_price` zostaje **celowo** bez adnotacji, bo `test_tools_route.py` pilnuje, że `read_only=None` jedzie jako „nie wiadomo", a nie jako zgadywanka |
| Niska | `teams/store.py:1208` (`_LATEST_RUN_STATUS_FOR_*`) | `ORDER BY f.fired_at DESC` bez `id` jako rozstrzygnięcia. Dwa wyzwolenia z tym samym znacznikiem czasu dałyby dowolne z nich jako „poprzedni przebieg". Wymaga dwóch wyzwoleń tego samego harmonogramu w tej samej mikrosekundzie, czego przejęcie w bazie i tak nie dopuszcza. | Świadomie zostawione |

Nic więcej z przeglądu diffu nie przeżyło weryfikacji.

## Spec coverage

### `teams-schedules` — testy w `modules/teams/tests/`

| Requirement / Scenario | Proven by |
|---|---|
| **Harmonogram należy do operatora, który go zapisał** | |
| Harmonogram cudzego operatora | `test_schedules_store.py::test_a_stranger_cannot_list_or_update_or_toggle_somebody_elses_schedule`, `test_schedules_routes.py::test_a_stranger_gets_404_for_a_schedule_that_is_not_theirs` |
| Przebieg z harmonogramu na liście przebiegów | `test_scheduler_clock.py::test_a_due_schedule_starts_a_run_and_records_the_fire` (przebieg powstaje z `owner_principal` harmonogramu); **„ślad wskazuje harmonogram" — GAP**, patrz niżej |
| **Harmonogram uruchamia rewizję przypiętą, a tryb „najnowsza" jest jawnym wyborem** | |
| Zespół zmieniony po zapisaniu harmonogramu | `test_scheduler_clock.py::test_a_due_schedule_starts_a_run_and_records_the_fire` (asercja `run["team_revision_id"] == revision_id`) |
| Harmonogram śledzący najnowszą rewizję | `test_schedules_store.py::test_updating_a_schedule_switches_it_to_tracking_latest`, `test_schedules_routes.py::test_a_schedule_tracking_latest_carries_no_pinned_revision` |
| **Wyzwolenie jest przejmowane dokładnie raz** | |
| Dwa procesy przy jednym wyzwoleniu | `test_schedules_store.py::test_two_processes_racing_the_same_due_schedule_give_exactly_one_winner` |
| **Pominięte wyzwolenia zwijają się do jednego** | |
| Moduł nie pracował przez sześć godzin | `test_scheduler_clock.py::test_a_schedule_far_overdue_still_produces_exactly_one_run`, `::test_next_fire_and_skipped_folds_every_due_slot_into_one`, `test_schedules_store.py::test_a_collapsed_fire_carries_how_many_were_skipped` |
| **Wyzwolenie bez przebiegu zostawia zapisany powód** | |
| Poprzedni przebieg wciąż trwa | `test_scheduler_clock.py::test_a_schedule_with_its_previous_run_still_working_is_skipped` |
| Zespół wyczerpał granicę dobową | `test_scheduler_clock.py::test_the_daily_cost_limit_stops_a_schedule_before_it_spends`; sufit zleceń z fazy 2: `::test_the_daily_order_limit_stops_a_schedule_and_leaves_a_row_rather_than_a_traceback` |
| Rewizja, której nie da się uruchomić | `test_scheduler_clock.py::test_a_revision_naming_a_model_outside_the_catalogue_is_skipped` |
| Niedostępność serwera narzędzi | `test_scheduler_triggers.py::test_a_trigger_with_no_tool_server_is_recorded_as_unavailable_not_false` — po stronie wyzwalacza; **po stronie harmonogramu GAP**, patrz niżej |
| **Harmonogram po serii nieudanych przebiegów wyłącza się sam** | |
| Kolejne przebiegi kończą się niepowodzeniem | `test_scheduler_clock.py::test_three_consecutive_failed_runs_disable_the_schedule`, `::test_a_completed_run_resets_the_failure_streak`, `test_schedules_store.py::test_re_enabling_a_schedule_clears_the_reason_and_the_failure_count` |
| **Harmonogram nad rewizją z narzędziami zapisującymi wymaga jawnego potwierdzenia** | |
| Rewizja z samym odczytem rynku | `test_schedules_routes.py::test_a_schedule_over_a_revision_carrying_only_read_tools_needs_no_ack`, `test_validation.py::test_a_revision_carrying_only_confirmed_read_only_tools_needs_no_acknowledgement` |
| Rewizja z narzędziem zmieniającym stan | `test_schedules_routes.py::test_a_schedule_over_a_revision_carrying_a_write_tool_is_refused_without_the_ack` (+ `::test_the_same_schedule_is_accepted_when_the_operator_acknowledges_it`), `test_validation.py::test_a_revision_naming_a_state_changing_tool_is_refused_without_acknowledgement`, `::test_a_tool_nobody_could_be_asked_about_is_refused_the_same_way` |
| **Moduł ma jeden zegar i sam publikuje najbliższe wyzwolenia** | |
| Operator pyta o najbliższe wyzwolenia | `test_schedules_routes.py::test_next_fires_preview_returns_the_requested_count_in_order` |
| Budzenie wyłączone ustawieniem | `test_scheduler_clock.py::test_a_disabled_clock_never_starts_a_background_task`; „ręczne uruchomienie działa dalej" wynika z tego, że `Clock.start()` jest jedyną rzeczą, którą flaga pomija — **nie ma osobnego testu** |
| **Przebieg z harmonogramu jest zwykłym przebiegiem** | |
| Operator przerywa przebieg, którego nie zaczął | Wspólna droga (`runner/starter.py::start_run_on_revision`, `RunRegistry`) — dowodzone testami przerwania z grupy 7 fazy 1, nie powtórzone tutaj |

### `teams-triggers`

| Requirement / Scenario | Proven by |
|---|---|
| **Warunek jest czytany narzędziami serwera narzędzi** | |
| Warunek nazywa wielkość spoza katalogu narzędzi | `test_schedules_routes.py::test_a_trigger_naming_an_unannounced_tool_is_refused` (przeciw prawdziwemu serwerowi MCP) |
| **Obserwowanie rynku nie kosztuje tokenów modelu** | |
| Warunek sprawdzany wielokrotnie bez spełnienia | `test_scheduler_triggers.py::test_a_condition_below_threshold_does_not_fire_or_cost_tokens` (asercja: zero wierszy `usage`) |
| **Wyzwalacz reaguje na zbocze, nie na stan** | |
| Warunek spełniony i pozostający spełniony | `test_scheduler_triggers.py::test_a_condition_crossing_the_threshold_fires_exactly_once` |
| Warunek migający wokół progu | `test_scheduler_triggers.py::test_a_flapping_condition_within_cooldown_is_suppressed` |
| **Niedostępność serwera narzędzi to nie jest niespełniony warunek** | |
| Serwer narzędzi nie odpowiada | `test_scheduler_triggers.py::test_a_trigger_with_no_tool_server_is_recorded_as_unavailable_not_false`, `test_schedules_store.py::test_a_condition_the_tool_server_could_not_answer_is_recorded_as_unknown` |
| Odmowa narzędzia zapisana odrębnie | `test_scheduler_triggers.py::test_a_refused_tool_call_is_recorded_with_its_own_reason` — **częściowo**: odrębny jest tekst powodu, nie wartość `outcome` (świadome odejście od dosłownego brzmienia specyfikacji, opisane w `tasks.md` 4.5) |
| Moduł bez skonfigurowanego serwera narzędzi | `test_schedules_routes.py::test_a_trigger_with_no_tool_server_configured_is_refused` |
| **Wyzwalacz podlega tym samym granicom co harmonogram** | |
| Warunek spełnia się przy wyczerpanej granicy dobowej | `test_scheduler_triggers.py::test_a_previous_trigger_run_still_working_is_skipped` (pominięcie), `::test_three_consecutive_failed_runs_disable_the_trigger`, `test_schedules_routes.py::test_a_trigger_over_a_revision_carrying_a_write_tool_is_refused_without_the_ack`; **sam sufit dobowy dla wyzwalacza — GAP**: wspólna droga (`_start_from`) jest ta sama, dowiedziona po stronie harmonogramu |

### `terminal-teams-schedules` — testy w `modules/terminal/src/teams/`

| Requirement / Scenario | Proven by |
|---|---|
| **Harmonogramy zespołu są widoczne razem z jego przebiegami** | |
| Harmonogram wyłączony przez moduł | `SchedulesPanel.test.tsx::toggles enabled through the module and shows a disabled reason it wrote` |
| **Terminal nie liczy czasu wyzwolenia sam** | |
| Podgląd najbliższych wyzwoleń | `SchedulesPanel.test.tsx::previews the next several fires from the module when a schedule is opened, not from a local parser` (wartości, których żaden parser cron by nie wyliczył) |
| **Czas jest pokazany tak, żeby nie trzeba było go przeliczać** | |
| Operator w strefie innej niż UTC | `SchedulesPanel.test.tsx::shows the module's own timestamp in UTC and in the terminal's local time — never recomputed` |
| **Historia pokazuje także to, co się nie wydarzyło** | |
| Wyzwolenie pominięte | `SchedulesPanel.test.tsx::shows a fire that started nothing, with its reason and no way to watch it` |
| Wyzwolenie zakończone przebiegiem | `SchedulesPanel.test.tsx::leads to the run's own trace for a fire that started one, folded slots and all` |
| **Odmowa modułu jest pokazana słowami modułu** | |
| Odmowa z powodu narzędzia zmieniającego stan | `SchedulesPanel.test.tsx::shows the module's own refusal, unchanged` (zapis) oraz `::shows the module's own words when enabling is refused` (włączanie — dopisane w tym review) |

## Gaps

- **Przebieg od końca do końca na uruchomionym stosie (8.2) nie został wykonany.**
  Odhaczony jako decyzja operatora, nie jako zrobiony. Testy `-m db` pokrywają te same
  trzy sytuacje przeciw prawdziwej bazie i prawdziwemu serwerowi MCP, ale żadna z nich nie
  pokrywa zegara budzącego się samego w procesie App Service ani `SCHEDULER_ENABLED` na
  produkcji. To jedyna rzecz, która dziś stoi między fazą 3 a `SCHEDULER_ENABLED = "true"`.
- **„Ślad przebiegu wskazuje harmonogram, który go uruchomił"** jest spełnione tylko w
  jedną stronę: wiersz `schedule_fires` nazywa swój `run_id`, ale `runs` nie niesie
  `schedule_id` (świadoma decyzja z `design.md`, „Trzy nowe tabele, zero zmian w tabelach
  fazy 1"), więc otwarty przebieg nie mówi, że przyszedł z zegara. Do zamknięcia albo
  kolumną, albo odczytem wstecz przez `schedule_fires` w `RunOut`.
- **Niedostępność serwera narzędzi jako powód pominięcia po stronie *harmonogramu***
  nie ma testu. Ścieżka istnieje — `execute_run` odmawia przebiegu, którego narzędzi nie
  potwierdzono — ale kończy się jako przebieg `failed`, nie jako `schedule_fires` z
  powodem, więc jest to raczej luka w implementacji niż w teście.
- **Podgląd najbliższych wyzwoleń działa tylko dla zapisanego harmonogramu.**
  `GET /schedules/{id}/next-fires` bierze `id`, więc przy zakładaniu nowego harmonogramu
  operator nie widzi nic, dopóki nie zapisze. Trasa przyjmująca samo wyrażenie cron
  zamknęłaby to bez przenoszenia liczenia do terminala.
- **„Ręczne uruchomienie przebiegu działa przy wyłączonym zegarze"** nie ma własnego
  testu; wynika z tego, że `SCHEDULER_ENABLED` pomija wyłącznie `Clock.start()`.

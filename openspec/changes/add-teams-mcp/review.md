## Verdict

Siódmy moduł stoi, dwanaście narzędzi odpowiada, a `agent` umie już dwa serwery narzędzi
zamiast jednego. Cała ścieżka — sesja MCP → `teams-mcp` → prawdziwy `teams` → prawdziwa
baza — została przejechana na uruchomionym stosie: katalog modeli, założenie zespołu dwóch
ról z krawędzią i granicą dobową, poprawka jednej roli (rewizja 2, druga rola i granica
nietknięte), harmonogram.

**Jedna rzecz, na której stoi cała decyzja D2, jest niesprawdzona — i to jest najważniejsze
zdanie tego dokumentu.** Czy Easy Auth przed `agent` przepuszcza oryginalny nagłówek
`Authorization`, i czy Easy Auth przed `teams` zamienia przeniesiony token na tożsamość
operatora. Lokalnie żadnego z nich nie ma, więc lokalny przebieg dowiódł instalacji
hydraulicznej i **nie** dowiódł mapowania tożsamości. Ryzyko jest ograniczone konstrukcją, a
nie nadzieją: bez tożsamości każde narzędzie odmawia, więc najgorszym możliwym skutkiem jest
moduł, który nie robi nic. Nie ma drogi, w której zapis trafia na złego właściciela. To jest
pierwsza rzecz do sprawdzenia po wdrożeniu, opisana niżej krok po kroku.

Czego tu nie ma i nie jest przeoczeniem: `terraform apply` (robota operatora, nigdy agenta),
wdrożenia obrazu, uruchomienia przebiegu na prawdziwym kluczu OpenAI (kosztuje pieniądze) i
sprawdzenia składni `dev.ps1` (brak `pwsh` na tej maszynie).

## Verified

Uruchomione, z wynikiem:

| Komenda | Wynik |
|---|---|
| `uv run pytest` (teams-mcp) | `63 passed` |
| `uv run ruff check .` · `uv run pyright` (teams-mcp) | `All checks passed` · `0 errors` |
| `uv run python scripts/contract.py check` (teams-mcp) | `Contract is up to date.` |
| `uv run pytest` (agent) | `337 passed` (przed zmianą 323) |
| `uv run ruff check .` · `uv run pyright` (agent) | `All checks passed` · `0 errors` |
| `terraform fmt -check -recursive` · `validate` | czysto · `Success` |
| `terraform plan` | `5 to add, 6 to change, 0 to destroy`, bez `azuread_*` poza nowym zestawem |
| `bash -n scripts/dev.sh` | czysto |
| `openspec validate add-teams-mcp --strict` | valid |

**Przebieg od końca do końca**, przez prawdziwą sesję MCP do `teams-mcp` i dalej do
uruchomionego `teams` z prawdziwą bazą (skrypt odgrywający to, co zrobi agent, minus model):

| Krok | Wynik |
|---|---|
| lista narzędzi | 12 |
| `list_models` | `gpt-5.6-luna` z katalogu `teams` |
| `create_team` | zespół `id=1`, rewizja 1, role `['scout','judge']` |
| `list_teams` | `['poranny przegląd']` |
| `revise_team` (jedna rola) | rewizja **2**, obie role, prompt scouta zmieniony |
| `read_team` | granica dobowa `1` **zachowana** mimo że łatka jej nie nazywała |
| `schedule_team` | `0 7 * * 1-5`, `next=2026-08-17T07:00:00Z`, ostrzeżenie o zegarze obecne |
| `list_schedules` | 1 |

Przebiegu (`run_team`) świadomie nie uruchomiono: kosztuje prawdziwe pieniądze na kluczu
OpenAI operatora, a ta sesja szła bez nadzoru. Ścieżka `run_team`/`read_run` jest pokryta
testami przeciw dublerowi.

## Findings

Znaleziska z self-review własnego diffu, po zamknięciu grup 1–10.

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Wysoka** | `agent/routers/sessions.py` | Tura, która rzuciła **przed** własnym `try` w `run_turn`, nie zostawiała nic w kolejce, a strumień SSE czekał na zdarzenie, które nigdy nie przyjdzie — zawieszenie podtrzymywane keep-alive'ami, nie błąd. Defekt starszy niż ta zmiana: wystarczyłby serwer narzędzi rzucający przy pytaniu o katalog. Wyszedł, bo dubler w teście miał złą sygnaturę i cały plik testowy wisiał 10 minut. | FIXED — `_close_stream_if_the_turn_died` zamyka strumień błędem; test `test_a_turn_that_dies_before_it_can_report_closes_the_stream` |
| **Wysoka** | `teams_mcp/tools/catalogue.py` (`create_team`) | Zespół powstaje przy `POST /teams`, a narzędzie robiło potem drugie wywołanie po rewizję. Awaria tego drugiego dawała modelowi „nie udało się" — nad zespołem, który **już istnieje** — więc model zakładałby go po raz drugi. Dokładnie to podwojenie, przed którym broni reguła „zapisu się nie ponawia", popełnione przez samo narzędzie. | FIXED — odczyt rewizji w `try`, odpowiedź niesie `team_id` i zdanie „Do not create it again"; test |
| Średnia | `teams_mcp/tools/schedules.py` (`list_schedules`) | Jedno wywołanie HTTP na wiersz, w kolejce: dziesięć harmonogramów to dwadzieścia jeden podróży jedna po drugiej, każda z własnym trzydziestosekundowym sufitem, w środku jednego wywołania narzędzia, na które operator czeka. | FIXED — `asyncio.gather` |
| Średnia | `teams_mcp/tools/runs.py` (`read_run`) | Cztery niezależne odczyty tego samego przebiegu, sekwencyjnie — ten sam kształt, ograniczony do czterech. | FIXED — `asyncio.gather` |
| Niska | `teams_mcp/tools/catalogue.py` (`revise_team`) | Odczyt-modyfikacja-zapis bez blokady: dwie równoległe poprawki tego samego zespołu nałożą łatki na tę samą bazę. Nic nie ginie (rewizje są append-only, obie zostaną zapisane), ale druga poprawka opisze stan sprzed pierwszej. Wymaga dwóch rozmów o jednym zespole naraz. | Świadomie zostawione |
| Niska | `design.md`, D6 | „Katalog modeli i narzędzi jedzie w opisie `create_team`" okazało się niewykonalne: opis jest stałym łańcuchem w kodzie, a katalog jest konfiguracją **tamtego** modułu, czytaną w czasie działania. Wpisanie go na stałe byłoby kopią cudzego katalogu, której ta architektura zabrania. | FIXED w trakcie — dwa narzędzia więcej (`list_models`, `list_tools`), `design.md` poprawiony z uzasadnieniem |
| Niska | `teams_mcp/tools/schedules.py` | Ostrzeżenie o wyłączonym zegarze pada przy **każdym** zapisie, bo `teams` nie publikuje `SCHEDULER_ENABLED` nigdzie na drucie. Nadmiarowe ostrzeganie jest błędem precyzji; milczenie byłoby błędem faktu, i to jego dotyczy wymaganie. Domknięcie to jedno pole po stronie `teams`. | Świadomie zostawione, opisane w `README.md` modułu |

Jedno znalezisko z przeglądu `plan`, nie z kodu: `allowed_applications` przy `market-mcp`
i `trading-mcp` pokazuje się jako `(known after apply)`. Ich data source'y odczytują
tożsamości aplikacji, które ten plan zmienia; `principal_id` tożsamości SystemAssigned nie
rusza się przy zmianie ustawień, więc rozwiążą się do tych samych identyfikatorów. **Warto
je odczytać po `apply`** — to lista mówiąca, kto może złożyć zlecenie.

## Spec coverage

### `teams-mcp-tools`

| Requirement / Scenario | Proven by |
|---|---|
| **Zestaw jest zredukowany do zadań operatora** | |
| Zespół zakładany jednym wywołaniem | `test_catalogue_tools.py::test_create_team_saves_a_team_and_its_first_revision_in_one_call`; przebieg 10.1, krok 3 |
| Poprawka nie wymaga odczytania całej definicji | `::test_revise_team_replaces_one_role_and_keeps_the_rest`, `::test_revise_team_keeps_limits_that_were_not_named`, `::test_revise_team_adds_an_agent_whose_key_is_new` |
| **Narzędzie zapisujące jest oznaczone jako zmieniające stan** | |
| Katalog rozróżnia odczyt od zapisu | Sprawdzone na ogłoszonym katalogu: 12 narzędzi, `read_only` zgodne z podziałem (`READ_ONLY`/`WRITE` w `_shared.py`) — **luka w automatyzacji**, patrz „Gaps" |
| **Opis narzędzia jest częścią kontraktu** | |
| Opis niesie warunki odmowy | **GAP** — opisy niosą granice (`run_team`, `schedule_team`), ale żaden test tego nie wymusza |
| **Zestaw odpowiada na pytania o to, co się wydarzyło** | |
| Model czyta ślad zakończonego przebiegu | `test_run_tools.py::test_read_run_gathers_the_trace_and_the_cost` |
| Przebieg wciąż trwa | `::test_read_run_says_a_working_run_is_not_finished` |
| **Harmonogram przy wyłączonym zegarze mówi o tym wprost** | |
| Zegar wyłączony | `test_schedule_tools.py::test_saving_a_schedule_warns_that_the_clock_may_be_off` — **z zastrzeżeniem**: ostrzega zawsze, bo nie umie odczytać tego ustawienia |

### `teams-mcp-authorship`

| Requirement / Scenario | Proven by |
|---|---|
| **To, co powstaje z czatu, należy do operatora** | |
| Zespół widoczny w terminalu | Przebieg 10.2 — **tylko lokalnie**, gdzie wszystko jest `anonymous`; patrz „Gaps" |
| Przebieg na liście przebiegów operatora | Wynika z tej samej drogi; nie uruchomiono przebiegu |
| Cudzy zespół pozostaje niewidoczny | `test_client.py::test_a_404_reads_as_both_answers_at_once`, `test_catalogue_tools.py::test_somebody_elses_team_reads_as_one_that_does_not_exist` |
| **Brak tożsamości zatrzymuje zapis** | |
| Żądanie bez tożsamości | `test_operator.py::test_a_call_with_no_operator_header_is_refused_naming_the_absence`, `::test_a_blank_header_counts_as_absent` |
| Odczyt bez tożsamości | Ta sama ścieżka — `_call` pyta o token przed każdym wywołaniem, czytającym i zapisującym |
| **Tożsamość jest przenoszona, a nie odgadywana** | |
| Model podaje cudzą tożsamość w argumencie | `test_operator.py::test_the_modules_own_authorization_header_is_not_mistaken_for_the_operators`; żadne narzędzie nie ma takiego argumentu w ogłoszonym schemacie |
| **Moduł nie rozszerza uprawnień** | |
| Granica dobowa zatrzymuje przebieg | `test_run_tools.py::test_the_daily_cost_limit_refuses_the_run_naming_its_number` |
| Odmowa dociera słowami modułu | `test_client.py::test_a_refusal_travels_with_teams_own_words`, `test_catalogue_tools.py::test_create_team_refusal_names_the_agent_teams_named` |
| Token nie trafia do logu | `test_operator.py::test_the_operators_token_never_reaches_a_log_line` (przy `DEBUG`) |

### `teams-mcp-upstream-access`

| Requirement / Scenario | Proven by |
|---|---|
| Adres zdalny bez tożsamości / pętla bez tożsamości / oba tryby naraz | `test_config.py` — cztery testy |
| Kontrakt sprawdzany, nie zakładany | `test_contract.py::test_every_route_the_tools_use_is_in_the_snapshot`, `::test_the_snapshot_matches_what_teams_publishes_right_now` (marker `contract`) |
| Wołanie ma skończony czas; zapis bez ponowienia | `test_client.py::test_a_write_is_never_retried`, `::test_a_read_is_retried_once_on_a_server_error`, `::test_a_timeout_on_a_write_says_the_effect_is_unknown` |
| Odmowa odróżnialna od niedostępności | `test_client.py::test_a_refusal_travels_with_teams_own_words` vs `::test_an_unreachable_teams_is_unavailability_not_a_refusal` |

### `teams-mcp-transport`

| Requirement / Scenario | Proven by |
|---|---|
| Jeden transport | `test_transport.py::test_the_entrypoint_never_runs_the_stdio_transport` |
| Wołający spoza listy / z listy | `::test_request_without_identity_is_refused_when_required`, `::test_request_with_identity_is_not_refused_by_this_layer` — **na poziomie modułu**; sama lista jest w Terraformie i nie ma testu |
| Jedno wejście bez poświadczenia | `::test_health_needs_no_identity_even_when_required`, `::test_health_reveals_nothing_about_the_catalogue` |

### `agent-tool-access` (MODIFIED)

| Requirement / Scenario | Proven by |
|---|---|
| Jeden serwer skonfigurowany, drugi nie | `test_tool_registry.py::test_one_server_configured_and_the_other_absent_is_a_working_configuration` |
| Komunikat nazywa serwer | `::test_each_servers_mode_is_refused_on_its_own_terms` (3 przypadki), `test_tool_server.py` |
| Jeden serwer odpowiada, drugi nie | `::test_one_server_being_unreachable_leaves_the_others_tools_in_place` |
| Operator prosi o zespół przy nieosiągalnym katalogu | `::test_a_name_nobody_announces_is_an_outcome_not_an_exception` — narzędzie nie istnieje, więc model dostaje wynik, nie wyjątek. **Częściowo**: że agent *powie* o tym operatorowi, niesie prompt v10, nie test |

## Gaps

- **Mapowanie tożsamości przez Easy Auth jest niesprawdzone**, i to jest jedyna luka, która
  może unieważnić decyzję D2. Dwa pytania, oba do sprawdzenia po wdrożeniu, w tej kolejności:
  1. czy `agent` widzi oryginalny nagłówek `Authorization` (zadanie 1.1 — wymaga tymczasowej
     trasy diagnostycznej na produkcji);
  2. czy `teams` widzi tożsamość operatora, gdy `teams-mcp` przedstawi mu przeniesiony
     token — sprawdzalne bez żadnej trasy: założyć zespół z czatu i zobaczyć, czy
     `owner_principal` w bazie to operator, a nie `anonymous`.

  Jeśli pierwsze zawiedzie, wraca alternatywa A z D2 (nagłówek delegacji, któremu `teams`
  ufa od nazwanych wołających) i zmienia się wyłącznie grupa 5.
- **Lokalnie wszystko jest `anonymous`**, łącznie z terminalem, więc lokalny dowód własności
  jest spójny i słabszy niż brzmi: dowodzi, że token jedzie i nagłówki się nie mieszają, nie
  że tożsamość zostaje zamieniona.
- **`dev.ps1` nie ma sprawdzonej składni** — brak `pwsh` na tej maszynie. Zmiany są
  mechanicznym odbiciem tych z `dev.sh`, który przechodzi `bash -n`.
- **Lista dopuszczonych wołających nie ma testu** i nie może go mieć po stronie modułu:
  jest w `auth_settings_v2`, a moduł sprawdza tylko, czy jakakolwiek tożsamość została
  ustalona. Dowodem jest `plan`, a po wdrożeniu odczyt przez `az`.
- **Opisy narzędzi nie mają testu**, choć wymaganie mówi, że są częścią kontraktu. Dałoby
  się to sprawdzić (asercja na obecność słów o granicach w `inputSchema`/opisie), ale
  byłby to test na brzmienie zdania, więc świadomie go nie ma.
- **Wyścig przy `revise_team`** — opisany w „Findings", zostawiony.
- **Przebieg z prawdziwym modelem** nie został uruchomiony ani lokalnie, ani na produkcji.
  To jest ta sama rzecz, którą faza 3 zostawiła operatorowi, i najlepszy pierwszy ruch po
  wdrożeniu tej zmiany.

## Kolejność wdrożenia

Z `design.md`, „Migration Plan", z jedną rzeczą dopisaną po implementacji:

1. **B3** (`terraform apply`), odczyt pamięci — plan mówi `5 to add, 6 to change`;
2. **`apply` reszty infrastruktury** — App Service, tożsamość, Easy Auth, lista wołających
   po stronie `teams`; odczytać po nim `allowed_applications` przy `market-mcp` i
   `trading-mcp`;
3. **merge do `main`** — wdroży `teams-mcp` i `agent`;
4. **sprawdzić tożsamość** (luka wyżej, punkt 2) — założyć zespół z czatu i zajrzeć do
   `owner_principal`. Dopiero to potwierdza, że zmiana robi to, po co powstała;
5. `TEAMS_MCP_URL` w ustawieniach `agent` jest **ostatnie** i jest momentem, w którym
   narzędzia się pojawiają. Wycofanie to wyczyszczenie tej jednej zmiennej i restart.

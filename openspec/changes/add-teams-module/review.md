# Review

## Verdict

Moduł napisany w całości i zamknięty w kodzie: `modules/teams` stoi jako piąty moduł — własna
baza, własny klucz OpenAI, katalog zespołów jako graf z rewizjami, przebieg na LangGraphie
z limitem rund, czasu i kosztu, ślad pisany na bieżąco i strumień postępu. Terminal ma
zakładkę `teams` z canvasem, panelem agenta i monitorem przebiegu. Osiem nowych zdolności,
84 z 87 zadań odhaczonych w chwili przeglądu (grupa 12 — rozmieszczenie agentów — doszła po
nim, z komentarzy operatora do uruchomionej aplikacji, i domknięcie przenumerowało się
na 13).

**Moduł nie stoi w Azure.** `az webapp list -g rg-tradingcenter` (16 sierpnia 2026) oddaje
cztery aplikacje — gateway, market-data, market-mcp, agent — a `app-tradingcenter-teams` nie
istnieje. Kod infrastruktury jest napisany i przechodzi `terraform validate` (grupa 10), ale
`apply` jest robotą operatora i nie został zrobiony; `deploy-teams.yml` nie miał więc jeszcze
ani jednego przebiegu. To nie jest usterka tej zmiany, tylko stan, w którym ją zamykamy, i
odróżnia ten przegląd od przeglądu `agent`: tamten oglądał moduł po tygodniu pracy na
produkcji, ten ogląda moduł, którego produkcja jeszcze nie widziała.

Otwarte zostają 13.1 (zespół przykładowy) i 13.2 (przebieg od końca do końca na uruchomionym
stosie). Drugiego z nich ten przegląd nie mógł wykonać sam — stos uruchamia operator i tylko
on — i nie należy tego mylić z twierdzeniem niesprawdzonym.

Przegląd znalazł trzy realne defekty. Jeden jest w testach, nie w module, i objawia się
trzema czerwonymi testami na maszynie deweloperskiej przy zielonym CI. Dwa pozostałe są
w tej samej szczelinie — między strumieniem postępu a tym, co widzi operator — i oba dają
ten sam objaw: przebieg, który wygląda na zawieszony, choć nim nie jest.

Wszystkie trzy zostały naprawione tego samego dnia; opis każdego zostaje w brzmieniu,
w jakim je znaleziono, a co z nim zrobiono stoi w kolumnie `Status`.

## Verified

Uruchomione 16 sierpnia 2026 na `feat/teams-module`, commit `64b8665`:

- `modules/teams`: `uv run ruff check .` — czysto. `uv run pyright` — 0 błędów.
  `uv run pytest -q` — **218 passed, 3 failed**. `uv run pytest -m db -q` — **73 passed,
  3 failed**, przeciw prawdziwemu PostgreSQL-owi w kontenerze jednorazowym. Te same trzy
  testy w obu przebiegach; przyczyna niżej, w Findings, i nie jest nią kod modułu — te same
  testy uruchomione z katalogu, w którym nie ma `.env`, przechodzą (9 passed).
- `modules/terminal`: `pnpm test` — 796 passed w 54 plikach. `pnpm lint` — czysto.
  `pnpm typecheck` — czysto. `pnpm contract:check` — „Every contract is up to date",
  z czego wynika też, że wyjście dla `market-data` przeżyło uogólnienie generatora.
- `openspec validate add-teams-module --strict` — valid.
- Azure, odczytane wprost: `app-tradingcenter-teams` nie istnieje (patrz Verdict). Bazy
  `teams`, sekretu ani reguł zapory nie ma po co sprawdzać, dopóki nie ma aplikacji, której
  adresy wyjściowe je definiują.
- Nie uruchamiano: przebiegu przez wdrożoną aplikację, przebiegu przez uruchomiony lokalnie
  stos (12.2) i testów `live` — tych ostatnich moduł nie ma.

Po naprawach z kolumny `Status` i po grupie 12 (rozmieszczenie agentów, migracja `0004`),
tego samego dnia: `modules/teams` — 229 passed, ruff i pyright czysto; `modules/terminal` —
805 passed, lint, typecheck i `contract:check` czysto.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `modules/teams/tests/test_app.py`, `test_tools_route.py`, `test_catalogue_routes.py` | Trzy testy dowodzące stanu „serwer narzędzi nieskonfigurowany" ustawiają go przez `monkeypatch.delenv("MARKET_MCP_URL")`, a `Settings()` w `lifespan` czyta `.env` modułu. Zmienna usunięta z procesu odsłania wartość z pliku, zamiast jej brak: na maszynie z `.env` w kształcie z `.env.example` testy widzą prawdziwy market-mcp i czerwienią się (`assert [10 narzędzi] == []`). CI jest zielone, bo w CI nie ma `.env` — czyli zielone z tego samego powodu, dla którego jest ślepe. Dotknięte: `test_the_module_starts_with_no_tool_server_configured` (6.7), `test_no_tool_server_configured_announces_nothing_rather_than_failing`, `test_a_tool_no_server_announces_is_refused_naming_the_agent`. | FIXED: `tests/conftest.py::_no_developer_env` — autouse, blankuje `MARKET_MCP_URL`, `MARKET_MCP_SCOPE` i `DATABASE_USER` (pusta wartość wygrywa z plikiem, usunięcie go odsłania) i usuwa trójkę `AZURE_*`, która jest wyjątkiem: czyta ją `DefaultAzureCredential` wprost ze środowiska i pusty `AZURE_CLIENT_ID` jest dla niej zepsuty, nie nieobecny. Pusty adres jest już w module brakiem adresu i ma na to własny test (`test_config.py::test_a_blank_tool_server_url_means_unset`). Suita przechodzi teraz z `.env` na miejscu — 229 passed. Naprawione w `conftest.py`, a nie po jednej linii na fikstur: to nie jest usterka trzech testów, tylko cecha każdego, który buduje `Settings()` przez `lifespan`. `test_config.py` tej dziury nie miał — buduje `Settings(..., _env_file=None)`, czego przez `lifespan` zrobić się nie da. |
| **Low** | `modules/teams/teams/routers/runs.py:195-209` | Strumień postępu zapisuje się na zdarzenia **po** odczytaniu migawki, nie przed. Komentarz nad `subscribe` mówi „subscribed before the snapshot is sent" — i to jest prawda o wysłaniu, a nie o odczycie: między `get_run_steps` a `subscribe` jest wyjście z `pool.acquire()`, czyli punkt zawieszenia, w którym trwający przebieg może opublikować `StepFinished`. Zdarzenie z tego okna nie trafia ani do migawki, ani do kolejki. Druga połowa tego samego: `finished` czytane jest z tamtego samego, już nieaktualnego wiersza, więc przebieg, który skończył się w tym oknie, zostawia strumień otwarty na zawsze — `RunFinished` i kończące `None` poszły, zanim kolejka istniała, a widz dostaje odtąd wyłącznie keep-alive. | FIXED: `subscribe` przed odczytem migawki, z oddaniem kolejki na drodze 404 (`runs.py`). Dowodzą tego dwa testy o samą kolejność i o brak porzuconej kolejki — `test_a_watcher_is_subscribed_before_the_snapshot_is_read`, `test_a_stranger_who_is_refused_leaves_no_watcher_behind` — bo okno jest jednym obrotem pętli zdarzeń i nie da się w nim usiąść. Cena przyjęta świadomie: zdarzenie może teraz trafić i do migawki, i do kolejki; krok, któremu dwa razy powiedziano, że skończył, dalej czyta się jako skończony. |
| **Low** | `modules/terminal/src/teams/useRunMonitor.ts:57-91`, `RunMonitor.tsx:134-139` | `runs.ts` opisuje kontrakt wprost: „a body that ends without `run_finished` is a dropped connection; the caller is where that becomes something the operator sees". Wołający tego nie robi — pętla `for await` kończy się, `status` zostaje `watching`, ostatnia migawka zostaje na ekranie, a przycisk „reload" pokazywany jest wyłącznie przy `status === "error"`. Zerwane połączenie w trakcie przebiegu wygląda dokładnie tak jak agent, który długo myśli. Wyjście jest — zamknięcie i ponowne otwarcie przebiegu przemontowuje monitor — ale nic operatorowi nie mówi, że ma go użyć. | FIXED: `useRunMonitor` pamięta, czy przebieg wciąż pracował i czy przyszło `run_finished`; bez tego drugiego przy pierwszym prawdziwym nazywa zerwanie i podnosi `status` na `error`, czyli pokazuje „Watch again". Ostatnia migawka zostaje na ekranie — banner jest dodatkiem, nie zamiennikiem. `TeamsView.test.tsx :: "says the connection was lost…"` i `:: "says nothing about a lost connection…"`. |

Przejrzane i odrzucone jako nie-znalezisko: zawężenie do poprzedników przy równoległych
agentach (stan LangGrapha trzyma pracę wszystkich, ale `_predecessors_of` jest jedynym
wejściem węzła — `test_run_graph.py::test_an_agent_is_given_nothing_from_an_agent_it_does_not_depend_on`);
strażnik kosztu liczący w pamięci zamiast czytać sumę z bazy (przebieg to jeden proces, a
wiersze lądują po wywołaniach — akumulator *jest* sumą); `>=` zamiast `>` przy granicy;
`_close` pod `asyncio.shield` przy przerwaniu; oraz to, że `GET /models` i `GET /tools` nie
biorą `current_principal` — publikują konfigurację modułu, nie dane operatora, i `agent`
ogłasza swój katalog dokładnie tak samo.

## Gaps

- **Granica dobowa jest sprawdzana przy starcie przebiegu i nigdzie indziej.** Dwa przebiegi
  tego samego zespołu uruchomione obok siebie czytają tę samą sumę sprzed obu i oba
  przechodzą; sufit jest wtedy przekraczalny przez zrównoleglenie. Wymaganie mówi
  o sprawdzeniu przed uruchomieniem i jest spełnione co do litery
  (`test_usage_route.py::test_a_team_that_used_up_its_day_cannot_start_another_run`), więc
  jest to luka w ochronie, nie niespełnione wymaganie — i taka, którą faza 3 (scheduler
  budzący zespoły w nocy) zamieni z teoretycznej w praktyczną.
- **„Przebieg kończy się rekomendacją, a nie zleceniem" nie ma własnego testu.** Dowód jest
  budowlany: jedynym serwerem narzędzi jest market-mcp, który jest tylko do odczytu
  (`market-mcp` spec), a ten moduł nie ma żadnego klienta `capital-gateway` — nie ma czego
  wywołać. Prompt mówi to samo (`test_run_loop.py::test_the_system_prompt_says_whether_this_run_has_tools`),
  ale prompt nie jest ochroną i nie jest tu za nią brany.
- **„Moduł jest właścicielem tego, co jego migracje tworzą" pilnuje operator, nie test.**
  Tabela stworzona tożsamością modułu należy do niego, ale że w bazie `teams` naprawdę
  wykonano `scripts/grant-schema-ownership.sql`, wie wyłącznie ten, kto to zrobił —
  i dopóki nie ma bazy, nie ma tego jak sprawdzić. To jest ta sama dziura, przez którą
  `agent` przewrócił się 15 sierpnia, tyle że tam objawiła się jako `permission denied`.
- **Lista dozwolonych adresów nie jest sprawdzana żadnym testem** — jak w `agent`.
  `test_no_cors.py` dowodzi tylko, że moduł świadomie nie dokłada własnego CORS; że lista
  w `infra/app-service.tf` zawiera adres terminala i nie zawiera `*`, wie `terraform plan`.
- **Zakładki `teams` nie oglądał człowiek w ramach tego przeglądu.** 796 testów terminala
  chodzi w jsdom, który nie ma układu ani szerokości, a canvas React Flow jest tam
  najbardziej wymagającą rzeczą, jaka do tej pory w tym terminalu stanęła.
- **Ani jeden prawdziwy przebieg zespołu nie odbył się w tym przeglądzie.** Wszystko, co
  dotyczy modelu, przechodzi przez `scripted_provider.py`; ile kosztuje i czy odpowiedzi
  składają się w cokolwiek sensownego, jest dokładnie tym, co ma powiedzieć 12.2.

## Spec coverage

Wymaganie po wymaganiu, z nazwanym dowodem. Wszystkie wymienione testy przechodzą
w przebiegu opisanym w `Verified`, poza trzema oznaczonymi ⚠ — te przechodzą w CI i na
maszynie bez `.env`, a czerwienią się lokalnie z powodu opisanego w Findings.

### `teams-catalogue`

| Requirement | Proven by |
|---|---|
| Definicja zespołu wystarcza, żeby zbudować z niej pracę | `test_contract.py::test_a_complete_agent_builds`, `::test_a_diamond_shaped_dag_is_valid`, `::test_a_single_agent_with_no_edges_is_valid`, `test_catalogue_routes.py::test_an_edge_survives_the_round_trip_under_its_wire_name` |
| Rewizja raz zapisana się nie zmienia | `test_store.py::test_saving_a_revision_leaves_the_previous_one_as_it_was`, `::test_the_latest_revision_is_the_newest_one_saved`, `test_catalogue_routes.py::test_saving_a_revision_appends_and_the_earlier_one_still_reads` |
| Definicja, której nie da się wykonać, jest odrzucana przy zapisie | `test_contract.py::test_a_simple_cycle_refuses`, `::test_a_three_node_cycle_refuses`, `::test_an_isolated_agent_among_connected_ones_refuses`, `::test_an_agent_depending_on_itself_refuses`, `test_catalogue_routes.py::test_a_dependency_cycle_is_refused_naming_the_agents_on_it`, `::test_an_agent_wired_to_nothing_is_refused_naming_it`, `::test_a_model_outside_the_catalogue_is_refused_naming_the_agent`, `::test_a_tool_no_server_announces_is_refused_naming_the_agent` ⚠, `::test_the_refusal_writes_nothing` |
| Katalog wystarcza, żeby wybrać zespół bez otwierania go | `test_store.py::test_the_catalogue_carries_the_latest_version_without_any_definition`, `test_catalogue_routes.py::test_the_catalogue_lists_what_the_operator_saved` |
| Zespół wycofany z katalogu nie zabiera ze sobą przebiegów | `test_store.py::test_retiring_a_team_takes_it_off_the_catalogue_and_leaves_its_runs`, `::test_retiring_a_retired_team_changes_nothing`, `test_catalogue_routes.py::test_a_retired_team_leaves_the_catalogue_but_keeps_its_revisions` |

### `teams-models`

| Requirement | Proven by |
|---|---|
| Katalog modeli wystarcza do zbudowania wybieraka | `test_models_catalogue.py::test_the_published_entry_carries_everything_a_picker_needs`, `::test_entries_come_cheapest_first`, `test_models_routes.py::test_the_catalogue_is_published_cheapest_first_with_its_rates` |
| Model wybiera się osobno dla każdego agenta | `test_models_routes.py::test_two_agents_in_one_team_may_carry_different_models`, `::test_an_agent_with_no_model_is_refused_naming_that_agent`, `test_models_catalogue.py::test_there_is_no_module_wide_default_to_fall_back_to` |
| Model spoza katalogu jest odmową, nie podmianą | `test_models_catalogue.py::test_a_model_outside_the_catalogue_raises_rather_than_substituting`, `test_validation.py::test_a_model_outside_the_catalogue_is_refused_naming_the_agent_and_the_model`, `test_runs_routes.py::test_a_revision_naming_a_model_since_withdrawn_cannot_be_run`, `test_models_routes.py::test_a_withdrawn_model_leaves_the_catalogue_and_its_revisions_readable`, `::test_a_revision_on_a_withdrawn_model_keeps_its_runs` |

### `teams-runs`

| Requirement | Proven by |
|---|---|
| Przebieg odbywa się na rewizji, nie na zespole | `test_runs_routes.py::test_saving_a_revision_mid_run_does_not_move_the_run` |
| Kolejność pracy agentów wynika z zależności | `test_run_graph.py::test_an_agent_waits_for_every_predecessor`, `::test_agents_without_a_dependency_between_them_work_at_the_same_time`, `test_run_engine.py::test_two_agents_of_one_run_can_work_at_the_same_time` |
| Agent widzi wypowiedzi poprzedników, a nie całą historię przebiegu | `test_run_graph.py::test_an_agent_is_given_nothing_from_an_agent_it_does_not_depend_on`, `::test_predecessors_arrive_in_the_definitions_own_order`, `test_run_loop.py::test_the_briefing_carries_predecessors_and_nothing_else`, `::test_an_agent_with_no_predecessors_is_told_so`, `test_run_engine.py::test_the_judge_is_briefed_with_what_the_scout_said` |
| Praca pojedynczego agenta ma skończoną liczbę rund | `test_run_loop.py::test_the_round_ceiling_stops_the_asking_and_shows_in_the_work` |
| Przebieg ma skończony czas i daje się przerwać | `test_run_engine.py::test_a_run_past_its_time_limit_is_stopped_naming_the_time`, `::test_an_interrupted_run_keeps_the_work_that_finished`, `test_runs_routes.py::test_an_operator_can_interrupt_a_run`, `::test_interrupting_a_finished_run_is_refused` |
| Ślad przebiegu zostaje niezależnie od tego, jak przebieg się skończył | `test_run_engine.py::test_a_broken_agent_fails_the_run_and_keeps_what_came_before`, `::test_a_tool_call_is_written_as_it_resolves`, `::test_a_finished_run_carries_every_agents_work`, `::test_runs_left_open_by_a_dead_process_are_closed` |
| Postęp przebiegu widać w trakcie, a nie dopiero po nim | `test_run_engine.py::test_a_watcher_sees_the_run_as_it_happens`, `::test_a_watcher_that_goes_away_does_not_stop_the_run`, `test_runs_routes.py::test_the_stream_opens_with_where_the_run_is_now`, `TeamsView.test.tsx :: "follows the run as it moves, without asking again"` — styku migawki z zapisem na zdarzenia nie trafia żaden z nich (Findings) |
| Przebieg kończy się zapisaną rekomendacją, a nie zleceniem | **luka** — dowód jest budowlany (jedyny serwer narzędzi jest tylko do odczytu, moduł nie ma klienta `capital-gateway`); `test_run_loop.py::test_the_system_prompt_says_whether_this_run_has_tools` mówi to promptem, co ochroną nie jest |

### `teams-tool-access`

| Requirement | Proven by |
|---|---|
| Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie | `test_config.py::test_remote_tool_server_without_a_scope_is_refused`, `::test_scope_with_a_loopback_tool_server_is_refused`, `::test_a_scope_with_no_url_at_all_is_refused`, `::test_loopback_tool_server_without_a_scope_is_accepted`, `::test_remote_tool_server_with_a_scope_is_accepted`, `::test_a_blank_tool_server_url_means_unset` |
| Agent dostaje narzędzia wskazane w definicji, a nie wszystkie | `test_tool_assignment.py::test_an_agent_gets_the_tools_the_definition_named_and_no_others`, `::test_the_order_is_the_definitions_own`, `::test_an_agent_carrying_no_tools_beside_one_that_does_gets_none` |
| Brak serwera narzędzi zatrzymuje przebieg | `test_tool_assignment.py::test_a_team_that_assigns_tools_is_refused_when_the_server_is_unreachable`, `::test_a_team_that_assigns_tools_is_refused_when_no_server_is_configured`, `::test_a_team_with_no_tools_runs_though_the_server_is_unreachable`, `::test_a_team_with_no_tools_runs_with_no_server_configured`, `test_run_engine.py::test_a_team_needing_tools_without_a_server_is_refused_before_any_agent_runs`, `test_app.py::test_the_module_starts_with_no_tool_server_configured` ⚠, `::test_a_tool_server_that_is_not_answering_does_not_stop_the_module` |
| Wołanie serwera narzędzi ma skończony czas | `test_tool_server.py::test_a_slow_server_times_out_as_unavailable_not_as_a_refusal`, `::test_an_unreachable_server_makes_a_call_unavailable_not_a_refusal`, `::test_an_unknown_tool_is_a_refusal_not_an_outage` |
| Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi | `test_tool_server.py::test_a_reworded_tool_needs_no_revision_rewritten`, `::test_the_tool_list_comes_from_the_server`, `test_tool_assignment.py::test_descriptors_come_from_the_session_not_from_the_revision`, `::test_a_tool_the_server_stopped_announcing_refuses_the_run`, `test_tools_route.py::test_what_the_server_announces_is_what_the_route_publishes`, `::test_a_configured_server_that_cannot_be_asked_is_an_outage_not_an_empty_list`, `::test_no_tool_server_configured_announces_nothing_rather_than_failing` ⚠, `pickersComeFromTheModule.test.ts :: "names no tool"` |

### `teams-usage`

| Requirement | Proven by |
|---|---|
| Każde wywołanie modelu zostawia własny wiersz zużycia | `test_run_loop.py::test_a_tool_round_bills_twice_and_leaves_a_call`, `test_usage_route.py::test_usage_is_broken_down_so_a_cost_can_be_put_on_a_role`, `::test_a_call_the_provider_reported_nothing_for_is_counted_as_unknown`, `::test_usage_of_one_run_is_not_the_usage_of_another` |
| Koszt jest przypisany do wiersza w chwili zapisu | `test_cost_ledger.py::test_a_price_change_does_not_move_what_earlier_rows_cost`, `test_contract.py::test_usage_out_keeps_a_missing_cost_as_none_not_zero`, `::test_usage_out_stringifies_cost` |
| Przekroczenie granicy kosztu zatrzymuje przebieg | `test_cost_limits.py::test_a_guard_stops_the_call_that_would_go_past_the_limit`, `::test_a_guard_with_no_limit_never_stops_anything`, `::test_a_call_with_no_reported_cost_adds_nothing`, `test_cost_ledger.py::test_a_run_that_reaches_its_limit_stops_and_says_so`, `::test_a_limit_that_is_not_reached_lets_the_run_finish`, `::test_todays_spend_is_what_the_daily_ceiling_reads`, `test_usage_route.py::test_a_team_that_used_up_its_day_cannot_start_another_run`, `::test_a_daily_limit_with_room_left_starts_the_run` — dobowa granica przy przebiegach równoległych jest luką opisaną w Gaps |

### `teams-database-connection`

| Requirement | Proven by |
|---|---|
| Moduł przedstawia się tożsamością, nie hasłem | `test_db.py::test_credential_selects_a_service_principal_when_all_three_are_given`, `::test_credential_rejects_a_partial_set`, `::test_token_provider_fetches_fresh_on_every_call`, `test_config.py::test_a_database_url_with_a_credential_refuses_to_start` |
| Połączenie z bazą zdalną jest szyfrowane | `test_config.py::test_a_database_url_that_does_not_require_tls_refuses_to_start`, `::test_local_mode_does_not_require_tls` |
| Praca bez tożsamości nie wychodzi poza maszynę | `test_config.py::test_no_database_user_with_a_remote_host_refuses_to_start`, `::test_a_blank_database_user_means_local_mode_not_a_role_named_blank`, `::test_no_database_user_with_a_loopback_url_is_local_mode` |
| Moduł nie dzieli bazy z innym modułem | `migrations/` modułu i `test_db.py::test_the_test_database_is_reachable`; rozdział ról i baz jest w `infra/database.tf`, nie w teście |
| Poświadczenie nie wycieka do logów | `test_db.py::test_a_connection_failure_is_logged_without_the_credential`, `::test_connection_target_names_host_port_and_database_never_a_credential` |
| Moduł sam doprowadza bazę do rewizji, dla której powstał | `test_migrate.py::test_an_empty_database_is_brought_to_head`, `::test_a_database_already_at_head_is_left_alone` |
| Migruje dokładnie jeden proces naraz | `test_migrate.py::test_the_lock_is_taken_and_released_around_a_real_migration`, `::test_the_lock_is_released_when_the_body_raises`, `::test_a_lock_that_never_frees_up_refuses_rather_than_waits_forever` |
| Moduł jest właścicielem tego, co jego migracje tworzą | **luka** — własność wynika z tego, że tabelę tworzy tożsamość aplikacji, a przygotowanie bazy to jednorazowy krok operatora (`scripts/grant-schema-ownership.sql`); żaden test go nie pilnuje i nie ma jeszcze bazy, na której dałoby się to odczytać |
| Moduł, który nie zdołał zmigrować, nie udaje że działa | `test_app.py::test_a_schema_the_image_was_not_built_for_refuses_to_start`, `test_schema_version.py::test_a_database_one_migration_behind_refuses_to_start`, `::test_a_database_ahead_of_the_image_refuses_too`, `::test_a_database_that_was_never_migrated_says_so`, `::test_a_missing_version_table_reads_as_no_revision_rather_than_an_error` |

### `teams-browser-access`

| Requirement | Proven by |
|---|---|
| Zespół i jego przebiegi należą do operatora, który je zapisał | `test_store.py::test_a_team_belonging_to_someone_else_reads_as_missing`, `::test_a_stranger_cannot_append_a_revision`, `::test_a_stranger_cannot_retire_a_team`, `test_catalogue_routes.py::test_someone_elses_team_answers_exactly_like_a_missing_one`, `::test_someone_elses_revision_by_id_answers_like_a_missing_one`, `test_runs_routes.py::test_a_strangers_run_reads_exactly_like_one_that_does_not_exist`, `::test_a_strangers_run_cannot_be_interrupted`, `::test_a_strangers_stream_is_refused`, `test_usage_route.py::test_a_stranger_sees_none_of_it` |
| Moduł nie bierze na wiarę warstwy przed sobą | `test_auth.py::test_no_identity_with_the_requirement_on_is_refused`, `::test_no_identity_and_no_requirement_is_the_local_identity`, `::test_the_principal_id_header_is_used_when_present`, `::test_the_name_header_is_a_fallback`, `::test_headers_arrive_however_starlette_normalises_them` |
| Wywołanie z przeglądarki przychodzi z uznanego adresu | **luka** — `test_no_cors.py::test_the_app_adds_no_cors_middleware_of_its_own` dowodzi tylko, że moduł świadomie nie dokłada własnego CORS; lista adresów jest w `infra/app-service.tf` i pilnuje jej `terraform plan` |
| Poświadczenie nie wędruje w adresie | `teamsApi.test.ts` — strumień przebiegu idzie przez `http.send` i `response.body`, czyli `fetch`/`ReadableStream`, nie `EventSource`; poświadczenie jedzie nagłówkiem tym samym klientem co reszta modułów |
| Poświadczenia nie trafiają do logów ani do odpowiedzi | `test_db.py::test_a_connection_failure_is_logged_without_the_credential`, `test_config.py::test_a_missing_api_key_refuses_to_start`, `::test_a_blank_api_key_is_a_missing_one_not_a_key_named_blank` |

### `terminal-teams`

| Requirement | Proven by |
|---|---|
| Zespół jest widoczny jako obraz zależności, nie jako lista ról | `TeamsView.test.tsx :: "shows every agent with its role and the model it works on"`, `teamDraft.test.ts :: "puts each agent one column past the ones it waits for"`, `:: "stacks agents that wait for nothing in the same column"`, `:: "still answers for a draft carrying a cycle"` |
| Operator składa zespół w tym samym widoku, w którym go ogląda | `TeamsView.test.tsx :: "adds an agent without leaving the view"`, `:: "removes a dependency from the agent it belongs to"`, `teamDraft.test.ts :: "takes every dependency touching it with it"`, `:: "ignores an agent depending on itself"`, `:: "ignores the same dependency drawn twice"`, `:: "changes only the one named"` |
| Zapis odrzucony przez moduł jest pokazany przy miejscu, którego dotyczy | `TeamsView.test.tsx :: "shows the module's reason and opens the agent it names"`, `refusal.test.ts :: "finds the agent a model refusal names"`, `:: "finds the dependencies a cycle runs through"`, `:: "does not read agent-1 out of a message about agent-10"`, `:: "keeps a message naming nothing it recognises, rather than replacing it"` |
| Katalog pokazuje, co jest do uruchomienia | `TeamsView.test.tsx :: "lists what the module published, without reading any definition"`, `:: "says so plainly when there is nothing saved yet"`, `:: "starts it from the catalogue and opens the run on the team's picture"`, `:: "shows the module's refusal rather than a run that is not there"` |
| Przebieg widać na obrazie zespołu w trakcie, nie po fakcie | `TeamsView.test.tsx :: "says who has finished, who is working and who is still waiting"`, `:: "follows the run as it moves, without asking again"`, `:: "hands over what an agent produced and what it called"`, `:: "shows the run as it stands now when it is opened again, not as it was"`, `:: "draws the revision the run works on, not the team's latest"`, `runs.test.ts :: "reads the opening snapshot into the run and its steps"` — zerwanie strumienia w trakcie nie jest pokazywane (Findings) |

Poza czterema lukami nazwanymi wyżej każde wymaganie ma nazwany dowód.

## Follow-ups

- ~~Trzy znaleziska z tabeli~~ — zamknięte tego samego dnia, każde ze swoim testem;
  szczegóły w kolumnie `Status`.
- 13.1 i 13.2 — zespół przykładowy i przebieg od końca do końca na uruchomionym stosie.
  Drugie z nich jest jedyną rzeczą, która powie, ile taki przebieg naprawdę kosztuje;
  granice kosztu są przetestowane, ale nigdy nie widziały prawdziwej stawki.
- `terraform apply` operatora, `scripts/grant-schema-ownership.sql` na bazie `teams`,
  i dopiero po nich pierwszy przebieg `deploy-teams.yml`. Do tego czasu moduł jest kodem,
  nie usługą — i przegląd tego nie ukrywa.
- Granica dobowa przy przebiegach równoległych: do zamknięcia razem z fazą 3, która
  z teoretycznego wyścigu robi nocny scenariusz.

## Verdict

Wdrożone: `modules/market-mcp` — piąty moduł, serwer MCP nad archiwum `market-data`, bez
bazy, bez stanu, bez migracji. Dziesięć narzędzi, wszystkie czytające, publikowane
identycznie dwiema drogami (stdio dla klienta na biurku, streamable http dla usługi w
innym kontenerze). Każda odpowiedź ma wpisany sufit i streszcza się zamiast rosnąć, a
odcięcie zostawia po sobie zdanie. Niepewność archiwum — `uncovered`, `derived`,
`settled` — jedzie w treści, nie ginie w streszczeniu. Do archiwum idą wyłącznie
żądania czytające, sprawdzane w jednym miejscu, przez które przechodzą wszystkie.
Wszystkie pięć grup zadań zamknięte.

Ta zmiana szła równolegle z `add-agent-chat`, która weszła na `main` pierwsza. Merge
`main` do gałęzi jest częścią tego przeglądu: siedem plików wyliczających moduły —
`checks.yml`, oba skrypty `dev`, `infra/app-service.tf`, `CLAUDE.md`, `README.md`,
`docs/architecture.md` — rozjechało się dokładnie tam, gdzie każdy z nich wypisuje listę
modułów. Żaden plik należący do któregokolwiek z dwóch modułów nie miał konfliktu:
`market-mcp` i `agent` nie dzielą ani jednej linijki.

Przegląd znalazł jedną rzecz i jest to błąd tej zmiany, nie znaleziony wcześniej ani
przez testy, ani przez CI: transport sieciowy wiązał się z każdym interfejsem także
lokalnie. Naprawione, szczegóły w Findings.

## Verified

- `cd modules/market-mcp && uv run pytest -q` → `115 passed`
- `cd modules/market-mcp && uv run ruff check .` → `All checks passed!`
- `cd modules/market-mcp && uv run pyright` → `0 errors, 0 warnings, 0 informations`
- `cd modules/market-mcp && uv run python scripts/contract.py check` → `Contract is up to date.`
- `cd infra && terraform validate` → `Success! The configuration is valid.`
- `cd infra && terraform fmt -check -recursive` → czysto
- `bash -n scripts/dev.sh` → czysto; `dev.ps1` przez `[Parser]::ParseFile` → bez błędów
- `checks.yml` i `deploy-market-mcp.yml` sparsowane jako YAML
- `openspec validate add-market-data-mcp --strict` → `Change 'add-market-data-mcp' is valid`

Windows 11. Testy modułu nie potrzebują ani Dockera, ani działającego archiwum —
`respx` podstawia `market-data`, a sprawdzenie kontraktu czyta `market_data.contract`
jako podproces w katalogu siostrzanym. Testów `live` ten moduł nie ma i nie potrzebuje:
nie dotyka żadnego dostawcy.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **Medium** | `modules/market-mcp/market_mcp/__main__.py`, `server.py` | Transport `http` wiązał się z `0.0.0.0` wpisanym na sztywno, więc uruchomiony lokalnie — a `scripts/dev.ps1` i `dev.sh` uruchamiają właśnie ten transport — publikował narzędzia na każdym interfejsie maszyny. Lokalnie `REQUIRE_AUTHENTICATED_PRINCIPAL` jest wyłączone z definicji (nic nie stoi z przodu), więc nie było przed tym żadnej drugiej bramki: w obcej sieci wystarczyło znać port. Pozostałe trzy moduły nie mają tego problemu przypadkiem, tylko dlatego, że startują przez CLI uvicorna, którego własna domyślna wartość to `127.0.0.1`, a `--host 0.0.0.0` jest dopisane w `CMD` ich obrazów. Ten moduł uruchamia uvicorna z Pythona (owijka tożsamości musi zbudować aplikację ASGI najpierw), więc odziedziczył tylko tę połowę wzorca, w której adres jest wpisany ręcznie. Naprawione: `mcp_http_host` w `config.py` z domyślną pętlą zwrotną, `ENV MCP_HTTP_HOST=0.0.0.0` w `Dockerfile` jako jawne nadpisanie kontenera, test na domyślnej wartości, wpis w `.env.example` i w `README.md`. | fixed |

## Deviations from design.md

- **Kolejność startu w skryptach `dev` jest inna, niż zapowiadało zadanie 5.7.** Zadanie
  mówiło „start po `market-data`, przed agentem"; grupa 5 wdrożyła „przed terminalem",
  bo agenta jeszcze na tej gałęzi nie było. Po merge'u `main` kolejność jest ta z
  zadania: `market-data → market-mcp → agent → terminal`. Nic w module nie zależy od
  tego, gdzie w tej kolejce stoi — nikt na niego nie czeka.
- **`market_mcp/tools.py` rozbite na pakiet, zanim urosło.** Odnotowane już w
  `tasks.md` przy grupie 3: ten sam podział, który ma `market_data/routers/`.
  `indicators.py` ma 710 linii i jest największym plikiem modułu — to jest miejsce, w
  którym następny podział będzie potrzebny, jeśli dojdzie piąty kształt wyjścia.

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **market-mcp-tools: Zestaw narzędzi wyłącznie czyta** | |
| Lista narzędzi nie zawiera zapisu | `tests/test_tool_surface.py::test_the_expected_tools_and_no_others` (dokładnie 10 nazw, żadnej innej), `::test_every_tool_is_marked_read_only` (`readOnlyHint=True` — dowód strukturalny, nie nazewniczy) |
| Model prosi o skasowanie danych | brak narzędzia zapisującego dowiedziony wyżej; `INSTRUCTIONS` w `server.py` nazywa to granicą modułu, nie chwilową odmową. Zachowanie samego modelu nie jest tu testowalne — patrz Gaps |
| **market-mcp-tools: Zestaw odpowiada na pytania o archiwum** | |
| Model zaczyna bez wiedzy o symbolach | `tests/test_search_instruments.py::test_search_returns_matches`, `tests/test_list_tracked_pairs.py::test_list_tracked_pairs_reads_market_data`, prompt `analyze-symbol` w `tests/test_resources.py::test_analyze_symbol_prompt_orders_the_steps` |
| Ostatnia cena niesie swój wiek | `tests/test_get_last_price.py::test_last_price_carries_its_age`, `::test_last_price_takes_the_newest_candle` |
| Pytanie o parę, której nikt nie zbiera | `tests/test_get_last_price.py::test_no_candle_for_untracked_pair`, `tests/test_get_candles.py::test_empty_series_for_untracked_pair_names_it_not_quiet`, `tests/test_uncertainty.py::test_untracked_pair_says_nobody_collects_it` |
| **market-mcp-tools: Zestaw odpowiada na pytania o wskaźniki** | |
| Katalog wystarcza do zbudowania żądania | `tests/test_indicators_catalogue.py::test_list_indicators_reads_the_whole_catalogue`, `::test_describe_indicator_returns_full_entry`, `::test_list_indicators_filters_by_group` |
| Wskaźnik spoza katalogu | `tests/test_compute_indicators.py::test_unknown_indicator_is_refused_with_a_hint`, `tests/test_indicators_catalogue.py::test_describe_unknown_indicator_points_at_the_catalogue`, `::test_describe_by_alias_names_the_canonical_id` |
| Wynik zredukowany domyślnie, seria na żądanie | `tests/test_compute_indicators.py::test_latest_mode_reports_value_slope_and_distance`, `::test_series_mode_thins_a_large_series`, `::test_invalid_mode_is_refused` |
| **market-mcp-tools: Opis narzędzia jest częścią kontraktu** | |
| Narzędzie bez kompletnego opisu | `tests/test_tool_surface.py::test_every_tool_has_a_description`, `::test_every_parameter_is_typed`, `::test_every_ceiling_is_named_in_the_description` |
| Czas jest jednoznaczny | `tests/test_tool_surface.py::test_time_tools_name_the_timezone`, `::test_price_tools_name_which_side_of_the_spread` |
| **market-mcp-answers: Odpowiedź ma sufit, a odcięcie nie jest ciche** | |
| Zakres większy niż sufit świec | `tests/test_get_candles.py::test_series_above_ceiling_is_aggregated_and_named`, `::test_small_series_is_returned_unaggregated`, `tests/test_reduce.py::test_series_above_target_is_bucketed`, `::test_bucket_merges_ohlc_correctly` |
| Lista poziomów dłuższa niż sufit | `tests/test_levels_near_price.py::test_merges_levels_zones_and_markers_sorted_by_distance`, `tests/test_reduce.py::test_truncate_over_limit_names_what_it_drops`, `tests/test_describe_coverage.py::test_coverage_beyond_the_limit_is_truncated_and_named`, `tests/test_search_instruments.py::test_search_beyond_the_limit_is_truncated_and_named`, `tests/test_compute_indicators.py::test_markers_are_capped_to_the_freshest_and_named` |
| Żądanie nie do streszczenia | `tests/test_get_candles.py::test_series_far_above_ceiling_is_refused_with_guidance`, `tests/test_compute_indicators.py::test_too_many_specs_is_refused` |
| Budżet znaków całej odpowiedzi | `tests/test_get_candles.py::test_a_years_daily_window_stays_within_a_character_budget` |
| **market-mcp-answers: Niepewność archiwum jedzie w treści odpowiedzi** | |
| Zakres z niezweryfikowanym przedziałem | `tests/test_get_candles.py::test_uncovered_range_is_named_in_the_reply`, `tests/test_uncertainty.py::test_gap_names_the_stretch_and_warns_against_reading_it_as_quiet`, `::test_no_gaps_is_silent` |
| Seria policzona, nie zebrana | `tests/test_get_candles.py::test_derived_series_is_named_in_the_reply`, `tests/test_uncertainty.py::test_derived_names_the_resolution`, `::test_not_derived_is_silent` |
| Wskaźnik bez pełnej rozgrzewki | `tests/test_compute_indicators.py::test_unsettled_result_carries_its_own_note` |
| Pusta seria nie czyta się jak cisza rynku | `tests/test_get_candles.py::test_empty_series_for_untracked_pair_names_it_not_quiet`, `::test_empty_series_for_tracked_pair_points_at_coverage`, `tests/test_summarize_range.py::test_summary_of_empty_series_names_why` |
| **market-mcp-answers: Trzy rodzaje „nie wiem" są rozróżnione** | |
| Archiwum nie odpowiada | `tests/test_refusal_shape.py::test_reason_three_the_archive_did_not_respond`, `tests/test_client_resilience.py::test_timeout_is_a_tool_refusal_naming_the_failure`, `::test_unreachable_archive_is_a_tool_refusal` |
| Para niezbierana kontra rynek zamknięty | `tests/test_refusal_shape.py::test_reason_one_nobody_tracks_the_pair`, `::test_reason_two_the_window_is_unverified`, `::test_the_three_reasons_read_differently` (trzy zdania różnią się treścią, nie tylko istnieją), `tests/test_uncertainty.py::test_tracked_pair_with_no_candle_points_at_coverage` |
| **market-mcp-answers: Odmowa jest odpowiedzią o jednym kształcie** | |
| Odmowa niesie poprawkę | `tests/test_refusal_shape.py::test_every_tool_refuses_the_same_way` (7 narzędzi, parametryzowane), `tests/test_get_candles.py::test_series_far_above_ceiling_is_refused_with_guidance` |
| Odmowa archiwum przepisana | `tests/test_get_candles.py::test_archive_refusal_detail_reaches_the_caller`, `tests/test_compute_indicators.py::test_error_result_carries_the_archives_own_reason` |
| **market-mcp-upstream-access: Tryb połączenia jest wybrany jednoznacznie** | |
| Adres zdalny bez tożsamości | `tests/test_config.py::test_remote_url_without_scope_is_refused` |
| Pętla zwrotna bez tożsamości | `tests/test_config.py::test_loopback_without_scope_is_local_mode`, `::test_blank_scope_means_unset` |
| Oba tryby naraz | `tests/test_config.py::test_scope_with_loopback_url_is_refused`, `::test_remote_url_with_scope_is_accepted` |
| **market-mcp-upstream-access: Do archiwum idą wyłącznie żądania czytające** | |
| Klient odmawia żądania zmieniającego | `tests/test_client.py::test_delete_is_rejected_before_any_request`, `::test_post_outside_indicators_is_rejected`, `::test_post_with_nested_indicators_path_is_rejected` — odrzucenie przed otwarciem gniazda |
| Obliczenie wskaźników jest dozwolone | `tests/test_client.py::test_compute_indicators_is_allowed`, `::test_get_reaches_market_data` |
| **market-mcp-upstream-access: Kontrakt archiwum jest sprawdzany, nie zakładany** | |
| Pole znika z kontraktu | `tests/test_contract.py::test_every_read_field_is_published` (16 modeli), `::test_every_read_path_is_published` (6 ścieżek), `::test_snapshot_exists`; `scripts/contract.py check` w CI przed testami |
| Sprawdzenie bez działającego archiwum | cały `tests/test_contract.py` czyta commitowany snapshot; `scripts/contract.py` woła `market_data.contract` jako podproces w katalogu siostrzanym, bez bazy i bez serwera |
| **market-mcp-upstream-access: Wołanie archiwum ma skończony czas i jedno ponowienie** | |
| Archiwum nie odpowiada w czasie | `tests/test_client_resilience.py::test_timeout_is_a_tool_refusal_naming_the_failure` |
| Jednorazowa awaria serwera | `::test_a_single_5xx_is_retried_and_can_succeed`, `::test_a_persistent_5xx_is_returned_after_one_retry`, `::test_a_4xx_is_not_retried` |
| Granica współbieżności | `::test_concurrent_requests_are_capped` (mierzy szczyt, nie tylko istnienie semafora) |
| **market-mcp-transport: Dwa transporty, jeden zestaw narzędzi** | |
| Ten sam zestaw obiema drogami | `tests/test_transport_parity.py::test_stdio_and_streamable_http_publish_the_same_tools` — prawdziwy podproces stdio i prawdziwy `uvicorn.Server` na realnym porcie, nie asercja przez czytanie kodu |
| Narzędzie dołożone do zestawu | ten sam test: obie listy pochodzą z jednej rejestracji w `tools.register` |
| **market-mcp-transport: Żądanie z sieci niesie tożsamość wołającego** | |
| Wołanie bez tożsamości przy włączonym wymogu | `tests/test_network_identity.py::test_request_without_identity_is_refused_when_required`, `::test_request_with_identity_is_not_refused_by_this_layer` |
| Praca lokalna | `::test_request_without_identity_is_let_through_when_not_required` |
| Dziennik bez treści żądania | `::test_refusal_is_logged_without_leaking_the_request_body` |
| **market-mcp-transport: Zdrowie modułu da się sprawdzić bez sesji MCP** | |
| Sonda bez sesji | `tests/test_server.py::test_health_answers_without_an_mcp_session`, `tests/test_network_identity.py::test_health_needs_no_identity_even_when_required` |
| Sonda przy niedostępnym archiwum | `tests/test_server.py::test_health_answers_even_when_the_archive_is_unreachable` |

## Gaps

- **Moduł nie ma jeszcze wołającego.** `allowed_applications` w Easy Auth `market-mcp`
  trzyma własny client id jako zaślepkę — token aplikacji nigdy nie niesie własnego
  `appid`, więc nic realnego przez tę bramkę nie przejdzie, dopóki nie wpisze się tam
  tożsamości agenta. To jest świadome: `proposal.md` wypycha klienta MCP po stronie
  agenta poza zakres tej zmiany. Do tego czasu jedynym prawdziwym konsumentem jest
  klient MCP na biurku operatora, przez `stdio`.
- **Nie było przebiegu przeciw działającemu archiwum.** Wszystkie 115 testów podstawia
  `market-data` przez `respx`. Kontrakt jest sprawdzany przeciw prawdziwemu schematowi
  (nie przeciw wyobrażeniu o nim), ale zachowanie prawdziwego archiwum pod obciążeniem —
  a szczególnie to, czy sufit 10 s wystarcza na `POST /indicators` z dziesięcioma
  wskaźnikami na szerokim oknie — jest do zmierzenia po uruchomieniu stosu, nie do
  przewidzenia teraz.
- **Warstwa tożsamości sprawdza tylko `scope["type"] == "http"`.** Żądanie WebSocket
  przeszłoby bez sprawdzenia. Dziś nie ma czego przez nie dosięgnąć — aplikacja
  streamable-http nie rejestruje żadnej trasy WebSocket — ale gdyby kiedyś
  zarejestrowała, ta gałąź jest miejscem do poprawienia i nic tego nie przypomni.
- **„Odpowiedź nazywa to zakresem modułu, a nie chwilową odmową"** jest zachowaniem
  modelu, nie modułu. Moduł robi tu wszystko, co może: nie publikuje narzędzia
  zapisującego i mówi to wprost w `INSTRUCTIONS`. Czy model to powtórzy operatorowi,
  sprawdzi się dopiero na żywo.
- **Piąta aplikacja na planie B1 z jednym workerem.** Ta zmiana dokłada piątą, a
  `add-agent-chat` dołożyła czwartą — obie z tym samym zapisem w design.md, że nacisk
  jest do zmierzenia po wdrożeniu. Teraz są obie i pomiar jest jeden, nie dwa.

# Review

## Verdict

Faza 2 jest napisana w całości: szósty moduł `modules/trading-mcp` z jednym transportem
sieciowym, narzędziami rachunku i czterema narzędziami zapisującymi; w `teams` rejestr dwóch
serwerów narzędzi zamiast jednego, granice handlowe w rewizji, ślad handlowy we własnej
tabeli i trasa jego odczytu; w terminalu panel granic, oznaczenie narzędzi ruszających
rachunek i zlecenia widoczne przy agencie, który je złożył. Infrastruktura, CI i wdrożenie
też są — i tym razem, inaczej niż przy fazie 1, **`terraform apply` został wykonany**:
`app-tradingcenter-trading-mcp` stoi w Azure, `teams` ma ustawienia `TRADING_MCP_*`, a
gateway ma w zaporze 32 reguły dla adresów wyjściowych nowego modułu.

**Czego nie ma: obrazu.** App Service chodzi na zaślepce i odpowiada 503, dokładnie tak jak
`app-tradingcenter-teams` — `deploy-trading-mcp.yml` nie istnieje na `main`, a GitHub
rejestruje workflow wyłącznie z gałęzi domyślnej. To nie jest usterka tej zmiany, tylko
skutek przyjętej zasady „jeden merge do `main` na końcu", i dotyczy teraz dwóch modułów.

Otwarte zostają 11.1 (zespół przykładowy) i 11.2 (przebieg od końca do końca zakończony
zleceniem na koncie demo). **Zamknięte decyzją operatora, nie przeoczeniem:** rynek jest w
niedzielę zamknięty, a oba domykają się razem z fazą 3, która i tak dotyka tej samej ścieżki
uruchamiania przebiegu. Nie należy tego mylić z twierdzeniem niesprawdzonym — nikt nie
twierdzi, że przebieg przeszedł.

Przegląd znalazł sześć defektów i wszystkie sześć skupiały się wokół jednej obietnicy tego
modułu: że model odróżni „twoje żądanie było złe" od „nie mogłem zapytać". Pięć naprawionych
w kodzie, szósty — granica czasu — okazał się dobrą decyzją opartą na błędnej arytmetyce i
został zamknięty poprawionym uzasadnieniem, nie zmianą liczby.

## Verified

Uruchomione 17 sierpnia 2026 na `feat/teams-platform`, po naprawach z kolumny `Status`:

- `modules/trading-mcp`: `uv run ruff check .` — czysto. `uv run pyright` — 0 błędów.
  `uv run pytest -q` — **68 passed** (58 przed przeglądem; dziesięć nowych to testy
  znalezisk niżej). `uv run python scripts/contract.py check` — „Contract is up to date".
- `modules/teams`: `uv run pytest -q` — **337 passed**, razem z testami `db` przeciw
  prawdziwemu PostgreSQL-owi w kontenerze jednorazowym.
- `modules/terminal`: `pnpm test` — **853 passed** w 56 plikach; `lint`, `typecheck` i
  `contract:check` czysto.
- `openspec validate add-trading-tools --strict` — valid.
- `infra`: `terraform fmt -check`, `terraform validate`, a potem — po raz pierwszy w tej
  serii — `apply` w kolejności z README modułu: `-target=azurerm_linux_web_app.trading_mcp`
  (3 dodane, 5 zmienionych), następnie pełny `apply` (2 dodane, 7 zmienionych, **0
  usuniętych**).
- Azure, odczytane wprost po `apply`, a nie ze stanu Terraforma:
  `az webapp show` — aplikacja `Running`; `authsettingsV2` — `requireAuthentication: true`,
  `Return401`, `excludedPaths: ["/health"]`, `allowedApplications` z **jednym** wpisem
  `b4569a04-…`, który `az ad sp show` potwierdza jako `app-tradingcenter-teams`;
  32 reguły `AllowTradingMcp-*` w zaporze gatewaya; polityka Key Vaulta `Get`/`List` dla
  tożsamości modułu; `TRADING_MCP_URL` i `TRADING_MCP_SCOPE` w ustawieniach `teams`.
- `curl https://app-tradingcenter-trading-mcp.azurewebsites.net/health` — **503**, tak samo
  jak `teams`. To jest stan „aplikacja stoi, obrazu nie ma", nie usterka: zaślepka
  (`mcr.microsoft.com/appsvc/staticsite`) sklejona z adresem GHCR nie daje się pobrać, więc
  kontener nigdy nie wstaje. Oba moduły czekają na tę samą drogę bez merge'a.
- Nie uruchamiano: przebiegu przez wdrożoną aplikację, przebiegu od końca do końca na
  uruchomionym lokalnie stosie (11.2) ani żadnego zlecenia na koncie demo. Testów `live` ten
  moduł nie ma — każdy test dubluje gateway, i tam też sprawdzana jest bramka demo, bo nie ma
  gdzie indziej.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| **High** | `trading_mcp/tools/_shared.py:82` | `_write` uznawał za awarię dostępu wyłącznie `5xx`, więc **401 od gatewaya — odrzucone poświadczenie tego modułu — docierał do modelu jako odmowa zlecenia**. Nikt wtedy nie spojrzał na treść żądania, a agent dostaje sygnał „popraw zlecenie" i spala rundy na poprawianiu czegoś, co nie było problemem. Spec zabrania tego wprost („Odmowa narzędzia jest odróżnialna od awarii dostępu"). | FIXED: `GatewayRefused.is_access_failure` w `errors.py` — jedna lista (`5xx`, 401, 403, 408, 429) i jedno uzasadnienie, czytane przez oba seamy. Testy: `test_a_rejected_caller_key_is_an_access_failure_not_a_refusal`, `test_a_rate_limited_write_is_an_access_failure`, a z drugiej strony granicy `test_a_404_on_a_position_stays_a_refusal`. |
| **High** | `trading_mcp/tools/_shared.py:55` | `_read` zwijał **każdy** `GatewayRefused` do „refused: …", 401 i 503 włącznie — odczyt, który nigdy się nie odbył, czytał się jak odpowiedź o rachunku. Model pytający o pozycje przed decyzją dostawał zdanie o rachunku zamiast informacji, że rachunku nie widział. | FIXED: ta sama właściwość; odczyt niewykonany mówi teraz „access failure … Nothing was read". Test: `test_a_read_the_gateway_would_not_serve_is_an_access_failure`. |
| **High** | `trading_mcp/client.py:72` | `_demo_verified` zerowane było wyłącznie przy błędzie transportu, nigdy przy błędnej **odpowiedzi** — wbrew komentarzowi przy samym polu i wbrew README („re-checked after any failed call"). Gateway zrestartowany za App Service odpowiada 503, a nie `RequestError`, więc bramka demo pomijała ponowne sprawdzenie dokładnie w przypadku odzyskanego połączenia, dla którego istnieje. | FIXED: `_send` zeruje pamięć przy każdej odpowiedzi błędnej. Test: `test_an_error_response_also_forces_a_fresh_check`. |
| **Medium** | `trading_mcp/tools/orders.py:58` | `ensure_demo_environment()` wołane w każdym z czterech narzędzi zapisujących **poza** seamem `_write`, więc jego `GatewayError`-y były jedynymi w module docierającymi do wołającego bez tłumaczenia — bez słów „access failure" i bez tego, co w tym miejscu jest najważniejsze: że **nic nie zostało wysłane**. | FIXED: bramka przeniesiona do środka `_write`, cztery wywołania usunięte. Trzy własne komunikaty (nie-demo, nieosiągalny gateway, odmowa przy sprawdzeniu) i trzy testy: `test_a_live_account_is_refused_with_nothing_sent`, `test_an_unreachable_gateway_during_the_demo_check_says_nothing_was_sent`, `test_a_refused_demo_check_is_an_access_failure_not_an_order_refusal`. |
| **Medium** | `trading_mcp/tools/orders.py:39` | `place_order` przyjmował `level` i `good_till` przy zleceniu MARKET i przesyłał je dalej, a `capital_gateway/adapter.py` **milcząco je odrzuca**: MARKET buduje się z symbolu, kierunku, wielkości i stopów. Agent, który miał na myśli „kup, ale nie drożej niż", dostawał wykonanie po cenie rynkowej — a `level` w odpowiedzi to cena wykonania, więc nic w odpowiedzi nie mówiło, że jego pułap zignorowano. | FIXED: odmowa przed zbudowaniem żądania, nazywająca pominięte pola i obie drogi wyjścia (usunąć je albo poprosić o LIMIT/STOP). Testy: `test_a_market_order_with_a_level_is_refused_before_any_request`, `test_a_market_order_with_good_till_is_refused_and_names_it`. |
| **Low** | `trading_mcp/config.py:31` | Uzasadnienie granicy 30 s liczyło pętlę potwierdzeń gatewaya jako „5 prób × 0,4 s", podczas gdy 0,4 s to *przerwa między* próbami, a każda próba jest własnym wywołaniem HTTP ograniczonym 20 s — prawdziwy najgorszy przypadek to ~122 s, nie ~22 s. | FIXED (komentarz, nie liczba): 30 s zostaje i jest teraz uzasadnione tym, czym naprawdę jest — pokryciem *zwykłego* najgorszego przypadku. Przypadek patologiczny to gateway, który sam ma kłopot, a odpowiedź modułu w tej sytuacji („skutek nieznany, przeczytaj pozycje, nie powtarzaj") jest prawdziwa; czekanie dwóch minut kupuje precyzję kosztem 15-minutowego sufitu przebiegu. `teams` trzyma swój sufit tuż za tym (35 s), więc warstwy zostają w tej kolejności. |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| **trading-mcp-transport** — Moduł wystawia jeden transport i jest nim sieciowy | `test_transport.py::test_the_entrypoint_takes_no_transport_argument`, `::test_the_entrypoint_never_runs_the_stdio_transport` |
| — Wołający jest wskazany imiennie / Wywołanie bez ustalonej tożsamości | `test_network_identity.py::test_request_without_identity_is_refused_when_required` |
| — Wywołanie od modułu spoza listy | `authsettingsV2` odczytane po `apply`: `allowedApplications` = jeden wpis (`teams`). Egzekwuje to Easy Auth, nie kod modułu — testu jednostkowego nie ma i nie może mieć |
| — Zdrowie modułu da się sprawdzić bez sesji MCP | `test_network_identity.py::test_health_needs_no_identity_even_when_required`, `::test_health_reveals_nothing_about_the_account` |
| **trading-mcp-upstream-access** — Bez poświadczenia moduł nie wstaje | `test_config.py::test_missing_gateway_key_is_refused`, `::test_blank_gateway_key_is_refused` |
| — Poświadczenie wymagane niezależnie od adresu | `test_config.py::test_gateway_key_required_even_at_loopback`, `test_client.py::test_every_request_carries_the_gateway_key` |
| — Moduł pracuje wyłącznie na rachunku demonstracyjnym | `test_demo_guard.py::test_non_demo_environment_is_refused`, `test_order_tools.py::test_a_live_account_is_refused_with_nothing_sent` |
| — Gateway zmienia środowisko przy odzyskanym połączeniu | `test_demo_guard.py::test_a_failed_call_forces_a_fresh_check_next_time`, `::test_an_error_response_also_forces_a_fresh_check` |
| — Poświadczenie nie wychodzi poza moduł | `test_client.py::test_a_4xx_is_a_refusal_naming_the_detail` (treść z gatewaya, bez nagłówka); klucz nie występuje w żadnym `GatewayError` |
| **trading-mcp-tools** — Zestaw obejmuje rachunek, a nie rynek | `test_tool_surface.py::test_no_tool_answers_about_price_candles_or_indicators`, `::test_the_server_description_points_to_market_mcp_for_the_market` |
| — Narzędzie zapisujące jest oznaczone jako zmieniające stan | `test_tool_surface.py::test_read_tools_are_annotated_read_only`, `::test_write_tools_are_annotated_as_changing_state` |
| — Odmowa narzędzia jest odróżnialna od awarii dostępu | `test_order_tools.py::test_a_timeout_is_an_access_failure_with_unknown_effect`, `::test_a_rejected_order_never_reads_as_an_access_failure`, `::test_a_rejected_caller_key_is_an_access_failure_not_a_refusal`, `test_account_tools.py::test_a_read_the_gateway_would_not_serve_is_an_access_failure` |
| — Nieznany symbol jest odmową przed dotknięciem rachunku | `test_order_tools.py::test_provider_rejection_is_a_refusal_naming_the_symbol` — odmowa pochodzi z `REJECTED` providera, nie z osobnej walidacji (świadomie, patrz nota przy grupie 3) |
| **trading-mcp-execution** — Wynik rozliczony albo nazwany nierozliczonym | `test_order_tools.py::test_market_order_is_settled`, `::test_pending_settlement_is_unsettled_not_filled` |
| — Moduł nie ponawia zlecenia po własnej awarii | `test_order_tools.py::test_a_write_is_never_retried_by_this_module`, `test_client.py::test_a_write_is_never_retried_on_5xx`, `::test_a_write_is_never_retried_after_a_timeout` |
| — Wywołanie gatewaya ma skończony czas | `test_client.py::test_timeout_is_a_gateway_unavailable`; sama liczba i jej uzasadnienie — `config.py` (patrz ostatnie Finding) |
| **teams-tool-access** — Tryb połączenia wybrany jednoznacznie (4 scenariusze) | `teams/tests/test_config.py::test_remote_trading_mcp_without_a_scope_is_refused`, `::test_scope_with_a_loopback_trading_mcp_is_refused`, `::test_loopback_trading_mcp_without_a_scope_is_accepted`, `::test_both_servers_configured_independently_is_accepted` |
| — Nieosiągalny jest tylko serwer, z którego nikt nic nie ma | `teams/tests/test_tool_assignment.py::test_an_unreachable_second_server_does_not_stop_a_team_that_never_needed_it`, `::test_announced_snapshot_names_an_unreachable_configured_server` |
| — Ta sama nazwa z dwóch serwerów jest odmową | `teams/tests/test_tool_assignment.py::test_a_name_two_servers_both_announce_refuses_the_run_naming_both` |
| **teams-trading** — Rewizja niesie własne granice handlowe | `teams/tests/test_trading_limits.py::test_a_definition_with_no_trading_limits_is_valid`, `::test_only_the_size_limit_set_leaves_the_counts_unbounded` |
| — Każda granica daje się wyłączyć, moduł żadnej nie narzuca | `::test_a_guard_with_no_limits_never_stops_anything`, `::test_an_enormous_limit_is_taken_at_face_value`, `test_trading_trace.py::test_a_team_with_no_trading_limits_places_every_order_it_asks_for` |
| — Granica sprawdzana przed wywołaniem zapisującym | `::test_the_run_count_is_reached_at_the_limit_not_past_it`, `::test_an_oversized_order_does_not_count_against_the_run`, `test_trading_trace.py::test_an_oversized_order_is_refused_without_stopping_the_run` |
| — Granica dobowa sprawdzana przed utworzeniem przebiegu | `test_trading_trace.py::test_todays_orders_are_what_the_daily_ceiling_reads`, `::test_an_unsettled_order_still_counts_against_the_day` |
| — Każde wywołanie zapisujące zostawia własny wiersz śladu (3 scenariusze) | `test_trading_trace.py::test_a_placed_order_leaves_a_row_naming_the_agent_and_the_order`, `::test_a_read_tool_leaves_no_trade_row`, `::test_an_access_failure_leaves_the_row_as_unknown_not_as_failed`, `teams/tests/test_runs_routes.py::test_the_trades_of_a_run_are_readable_on_their_own_route`, `::test_a_strangers_trades_are_not_readable` |
| **teams-runs** — Ślad niesie pracę i zlecenie / przerwanie nie cofa zlecenia | `test_trading_trace.py::test_a_trade_row_survives_an_interrupted_run` |
| — Powód zatrzymania odróżnia granicę zleceń od kosztu | `test_trading_trace.py::test_a_run_reaching_its_order_limit_stops_and_says_orders_not_cost` |
| **teams-catalogue** — Granice handlowe są wyborem operatora, nie warunkiem zapisu | `test_trading_limits.py::test_a_definition_with_no_trading_limits_is_valid`, `test_trading_trace.py::test_a_revision_saved_before_trading_limits_existed_still_runs`, terminal: `TeamsView.test.tsx` → „saves an agent given a write tool and no limit at all" |
| **terminal-teams** — Złożone zlecenia widać przy agencie (2 scenariusze) | `TeamsView.test.tsx` → „shows an order beside the agent that placed it", „shows an order of unknown outcome as unknown rather than dropping it"; `runs.test.ts` → „shows an order of unknown outcome as unknown, not as a failure", „reads a row still saying `sent` by whether the run is over" |
| — Granice ustawia się w tym samym widoku (2 scenariusze) | `TeamsView.test.tsx` → „sets them in the same view the team is composed in", „marks the tools that move the account, and says when nobody annotated one" |
| — Zatrzymanie granicą zleceń pokazane jako takie | `TeamsView.test.tsx` → „names the order limit as the reason, apart from the cost, and lists what was placed"; `runs.test.ts` → „tells the order limit from the cost limit" |

## Gaps

- **11.1 i 11.2 zamknięte bez wykonania, decyzją operatora.** Zespół przykładowy i przebieg
  od końca do końca zakończony zleceniem na koncie demo domykają się razem z fazą 3; rynek w
  niedzielę jest zamknięty, a faza 3 dotyka tej samej ścieżki uruchamiania przebiegu. Nic w
  tej zmianie nie było sprawdzone przeciw prawdziwemu kontu — wszystko, co dotyczy gatewaya,
  przechodzi dziś przez dublera w testach.
- **Obrazu nie ma i nie da się go zbudować zwykłą drogą**, bo `deploy-trading-mcp.yml` nie
  istnieje na `main`. Droga bez merge'a jest ta sama co przy `teams` i jest opisana w
  `docs/teams-fazy-stan.html`: gałąź w filtrze `push:`, przebieg workflow, filtr z powrotem.
- **`allowed_applications` nie ma testu i mieć nie może** — egzekwuje to Easy Auth przed
  kontenerem. Dowodem jest odczyt z Azure w sekcji `Verified`, a nie zielony test.
- **Styk z fazą 3 zostaje otwarty:** `teams/validation.py` trzyma
  `STATE_CHANGING_TOOLS = frozenset()` z komentarzem „pusty, dopóki faza 2 nie doda
  pierwszego". Ta zmiana dodała `place_order` i oznacza narzędzia zapisujące flagą
  `read_only` na drucie — dopóki obie rzeczy nie zostaną spięte, harmonogram uruchomi zespół
  z narzędziami zapisującymi bez jawnego potwierdzenia, którego wymaga `teams-schedules`.
  Sprawdzenie istnieje, przechodzi testy i nie łapie niczego, bo pyta o pusty zbiór. Należy
  do fazy 3 i jest tam pierwszą rzeczą na liście.

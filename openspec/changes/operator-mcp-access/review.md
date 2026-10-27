## Verdict

Zmiana jest gotowa do merge, ale nie została zmergowana ani wdrożona. Dziewięć powierzchni narzędziowych produkcji
otwiera się dla jednej aplikacji z zewnątrz, Claude Code operatora. Chodzi o sześć pakietów workbencha,
`/strategies/mcp`, `/team-tools/mcp` i trading-mcp pod `/trading/mcp`. Każde wejście wymaga tokenu, roli `admin` i
aplikacji z listy. `terraform apply` i zmienna `CLAUDE_CODE_APPLICATION_ID` są krokami operatora. Plan Terraform
pokazuje dryf niezwiązany z tą zmianą (luka 1), który trzeba rozstrzygnąć przed `apply`.

## Verified

Uruchomione 26.10.2026 na gałęzi `feat/operator-mcp-access`, powtórzone 27.10 po poprawkach z code review
(tc-entra-auth 68, tc-mcp-kit 29, trading-mcp 114, workbench 3352 + 11 skipped, capital-gateway 269, scripts 220;
ruff i pyright czysto wszędzie):

- `packages/tc-entra-auth`: `uv run pytest` → 64 passed; `ruff check .` czysto; `pyright` → 0 errors.
- `modules/trading-mcp`: `uv run pytest` → 113 passed; `ruff check .` czysto; `pyright` → 0 errors.
- `modules/workbench`: `uv run pytest` (z Dockerem, więc także `db`) → 3352 passed, 11 skipped; `ruff check .` czysto;
  `pyright` → 0 errors.
- `modules/capital-gateway`: `uv run pytest` → 269 passed, 11 skipped. Konsument zmienionego `tc-entra-auth`.
- `scripts`: `uv run pytest` → 223 passed, 27 skipped; `ruff`, `pyright` czysto. Test
  `test_assemble_env.py::test_the_workflow_hands_the_script_exactly_the_names_it_reads` wyłapał brak nowej zmiennej w
  `deploy-vps.yml` i ten brak jest poprawiony.
- Terminal `node scripts/contract.mjs check` → „Every contract is up to date.”; pocket → „The contract is up to date.”
- `terraform validate` → Success. `terraform plan -lock=false` → 4 to add (rejestracja, SP, dwie pre-autoryzacje),
  **2 to destroy** — patrz luka 1.
- Caddy: `caddy validate` (obraz `caddy:2-alpine`) → Valid configuration. Do tego przebieg z prawdziwym Caddyfile
  przed trzema serwerami echo w Dockerze:
  - `/trading/mcp` → trading-mcp jako `/mcp` z `X-TC-Edge: 1`;
  - `/market/mcp` i `/team-tools/mcp` → workbench;
  - `/mcp` na hoście bramy → 404;
  - podrobiony `X-MS-CLIENT-PRINCIPAL` usunięty.
- Przebieg przez Claude Code: lokalny host zastępczy z prawdziwym pakietem `market_data` i prawdziwą powierzchnią
  `/team-tools`, za ich rekordami dostępu, a przed nimi atrapa drzwi. Claude Code dostał osobny `CLAUDE_CONFIG_DIR`:
  - `claude mcp list` → oba serwery „✔ Connected”, helper wywołany dla każdego adresu;
  - `claude -p` wywołał `list_models` i dostał `{"asked_by":"person-from-token"}`, czyli osoba z drzwi dotarła do trasy
    zespołów przez stanową sesję;
  - helper zwracający błąd daje w kliencie „Dynamic Client Registration rejected (HTTP 401)”.

## Findings

| Severity | Where | Finding | Status |
|---|---|---|---|
| Wysoka | `modules/trading-mcp/trading_mcp/__main__.py` | trading-mcp nie konfigurował logowania, więc root zostawał na WARNING. Każdy wpis INFO, w tym oba wpisy śladu zapisu, ginął na produkcji. Ślad wymagany przez spec istniałby tylko w testach. | FIXED przed commitem: `basicConfig(WARNING)` i `trading_mcp` na INFO |
| Średnia | `.github/workflows/deploy-vps.yml` | Krok „Assemble the environment” wylicza nazwy jawnie. Bez `CLAUDE_CODE_APPLICATION_ID` deploy odmówiłby z „missing”, mimo zmiennej ustawionej w środowisku. | FIXED (wyłapane przez `test_assemble_env`) |
| Wysoka | `deploy/scripts/fill-github-environment.sh` | Edycja zamieniła dosłowny CR w `tr -d` (`sp_of`, `role_of`) na znak nowej linii. Pod Git Bash na Windows identyfikatory dostępu trafiłyby do `vps` z końcowym CR. | FIXED 27.10: `tr -d '\r'`, jak w reszcie pliku |
| Średnia | `modules/trading-mcp/trading_mcp/tools/_shared.py` | Po wpisie „sending” brakowało wpisu skutku dla każdego innego wyjątku (anulowanie wywołania, nieczytelna odpowiedź 2xx). Zlecenie mogło dotrzeć na rachunek, a log kończył się na „sending”. | FIXED 27.10: `except BaseException` zapisuje „unknown (…)”; przypadek `[unreadable]` pada bez poprawki |
| Średnia | `scripts/mcp_token.py`, `scripts/claude-mcp.sh` | Helper zgadywał API z `CLAUDE_CODE_MCP_SERVER_URL`. Bez tej zmiennej `tc-trading` dostałby token workbencha i 401 opisane w kliencie jako nieudane logowanie. | FIXED 27.10: `--api workbench\|gateway` wpisane przy rejestracji serwera |
| Średnia | `deploy/scripts/fill-github-environment.sh` | `--display-name` w Graph to dopasowanie po prefiksie, a `[0]` po cichu wybiera jedną z kilku rejestracji. | FIXED 27.10: `displayName eq '…'` |
| Niska | `trading_mcp/trace.py`, `teams_tools/server.py` | Dwie kopie odczytu nagłówka z `request_ctx` i trzecia kopia dekodowania `X-MS-CLIENT-PRINCIPAL`. | FIXED 27.10: `tc_mcp_kit.tool_call.request_header`; `tc_entra_auth.application_in` czyta to, co pisze `principal_blob` |
| Niska | `workbench/team_tools.py`, `workbench/config.py` | `SurfaceCallers` powielał ustawienia procesu; `tool_caller_ids` miał własną kopię parsowania listy. | FIXED 27.10: `serving` dostaje `Settings`; jedno `_identifiers` |
| Niska | `trading_mcp/config.py`, `deploy/Caddyfile`, `infra/entra.tf`, `workbench/config.py` | Komentarze ponad limit dwóch linii; komentarz `server_mode` w trading-mcp mówił, że moduł nigdy nie jest na krawędzi. | FIXED 27.10 |
| Niska | `tc_entra_auth/edge.py` | `token_applications` w drzwiach zamiast w rekordzie wołających. | Świadomie zostawione: tylko drzwi wiedzą, czy tożsamość przyszła z tokenu czy z klucza, a lista dotyczy tylko tokenów |
| Niska | `trading-mcp/tests/test_external_callers.py` | Macierz drzwi powtórzona w konsumencie (reguła 5). | Świadomie zostawione: autoryzacja fail-closed i ścieżka zapisu trading-mcp są wyjątkami od reguł w CLAUDE.md |
| Niska | `workbench/team_tools.py`, `_ServerOnTheState` | Drugi forwarder obok `tc_mcp_kit.mounted_server._ToolSurface`. | Świadomie zostawione: serwer powstaje w lifespanie, a `_ToolSurface` wiąże go przy budowie |
| Niska | `deploy/Caddyfile`, `/trading/health` | Sonda trading-mcp jest osiągalna z zewnątrz bez poświadczenia. Odpowiada wyłącznie `{"status":"ok"}`, zgodnie z wymaganiem o sondzie. | Świadomie zostawione |

## Spec coverage

| Requirement / Scenario | Proven by |
|---|---|
| operator-tool-access · Krawędź… / Klient MCP pod adresem archiwum | `scripts/tests/test_deploy_compose.py::test_the_api_host_carries_the_tool_surfaces_and_trading_mcp_under_its_prefix`; przebieg Caddy w Dockerze (Verified) |
| operator-tool-access · Krawędź… / Ścieżka MCP na hoście bramy | `scripts/tests/test_deploy_compose.py::test_the_gateway_host_carries_neither_its_stream_nor_a_tool_surface` |
| operator-tool-access · Narzędzia z zewnątrz… / Token admina z aplikacji operatora | `modules/workbench/tests/test_server_mode.py::test_a_package_tool_surface_answers_from_outside_only_the_listed_client[operator-mcp-client-None]`; `modules/trading-mcp/tests/test_external_callers.py::test_the_operators_application_gets_past_the_door` |
| operator-tool-access · Narzędzia z zewnątrz… / Token przeglądarki terminala | `test_server_mode.py::test_a_package_tool_surface_answers_from_outside_only_the_listed_client[terminal-app-id-403]`; `test_external_callers.py::test_everyone_else_from_outside_is_refused[terminal-403]` |
| operator-tool-access · Narzędzia z zewnątrz… / Viewer | `modules/workbench/tests/test_roles.py::test_a_viewer_reaches_the_two_archives_for_reading_and_no_other_door` (`/strategies/mcp`, `/team-tools/mcp`, `/social/mcp`, `/polymarket/mcp`); `test_external_callers.py::test_everyone_else_from_outside_is_refused[viewer-403]` |
| operator-tool-access · Narzędzia z zewnątrz… / Brak tokenu | `packages/tc-entra-auth/tests/test_edge.py::test_the_edge_without_a_valid_token_is_refused`; `test_external_callers.py::test_everyone_else_from_outside_is_refused[forged-401]` |
| operator-tool-access · Narzędzia z zewnątrz… / Token wydany dla workbencha na `/trading/mcp` | Audiencję sprawdza `packages/tc-entra-auth/tests/test_verifier.py::test_a_token_failing_one_claim_is_refused[audience]`. Że trading-mcp dostaje audiencję bramy: `test_deploy_compose.py::test_the_tool_server_admits_from_outside_only_the_operators_client` |
| operator-tool-access · Operator dostaje token… / Token jest w pamięci podręcznej | `scripts/tests/test_mcp_token.py::test_a_cached_token_is_handed_over`, `::test_only_trading_mcp_is_registered_for_the_gateways_api` |
| operator-tool-access · Operator dostaje token… / Operator nie był zalogowany | `scripts/tests/test_mcp_token.py::test_without_a_usable_sign_in_it_refuses_and_names_login` |
| trading-mcp-transport · Wołający jest wskazany imiennie / Wywołanie bez ustalonej tożsamości | `modules/trading-mcp/tests/test_server_mode.py::test_the_tool_surface_refuses_all_but_a_service_with_the_key` |
| trading-mcp-transport · Wołający… / Wywołanie od modułu spoza listy | `test_external_callers.py::test_everyone_else_from_outside_is_refused[terminal-403]` |
| trading-mcp-transport · Wołający… / Token aplikacji spoza listy zewnętrznych wołających | j.w.; mechanizm: `packages/tc-entra-auth/tests/test_edge.py::test_a_token_is_admitted_only_from_a_listed_application` |
| trading-mcp-transport · Wołający… / Pusta lista zewnętrznych wołających | `test_external_callers.py::test_with_no_external_caller_named_a_token_opens_nothing` |
| trading-mcp-transport · Zapis… zostawia ślad / Zlecenie złożone z klienta operatora | `test_external_callers.py::test_a_write_is_traced_before_it_is_sent_and_after`, `::test_the_trace_names_the_caller_the_door_wrote` |
| trading-mcp-transport · Zapis… zostawia ślad / Brama nie odpowiada | `test_external_callers.py::test_a_write_whose_effect_is_unknown_is_traced_as_unknown[unreachable]`, `[unreadable]` |
| strategies-tools · Narzędzia strategii dostaje tylko rozmowa / Narzędzia dla agenta zespołu | `modules/workbench/tests/strategies/test_tools.py::test_a_team_gets_the_three_that_read_and_nothing_that_writes` |
| strategies-tools · … / Klient operatora pod `/strategies/mcp` | `test_tools.py::test_the_tools_are_served_over_the_network_to_a_listed_caller_alone[operator-mcp-client-False]` |
| strategies-tools · … / Wołający spoza listy | `test_tools.py::test_the_tools_are_served_over_the_network_to_a_listed_caller_alone[terminal-True]` |
| workbench-team-tools · Zestaw… przez sieć / Zespół założony z klienta operatora | `modules/workbench/tests/test_team_tools_surface.py::test_the_tool_acts_for_the_person_the_door_wrote` (osoba dociera do trasy `teams`) |
| workbench-team-tools · … / Wołający spoza listy | `test_team_tools_surface.py::test_a_caller_off_the_list_is_refused_before_any_tool` |
| workbench-team-tools · … / Wywołanie przez sieć bez tożsamości osoby | `test_team_tools_surface.py::test_without_a_person_the_tool_refuses_and_names_why` |

## Gaps

1. **Dryf w Terraform, niezwiązany z tą zmianą.** `terraform plan` chce zniszczyć `admin_workbench` i `admin_gateway`
   dla obiektu `73c09587-…`, czyli osoby, która ma rolę admin w stanie, a nie ma jej w lokalnym,
   nieśledzonym przez git `terraform.tfvars` (`admin_user_object_ids`). Zwykłe `apply` odebrałoby jej rolę. Przed `apply` trzeba dopisać ją do
   `admin_user_object_ids` albo zastosować tylko nowe zasoby:
   `-target=azuread_application.claude_code -target=azuread_service_principal.claude_code`
   `-target=azuread_application_pre_authorized.workbench_claude_code -target=azuread_application_pre_authorized.gateway_claude_code`.
2. „Zespół należy do osoby i jest widoczny w terminalu” jest udowodnione do granicy trasy `teams`: osoba z drzwi
   dociera do nagłówka, który trasy czytają. Własność wiersza w bazie dowodzą istniejące testy `teams`, nie nowy test
   przez sieć.
3. Brak testu, że ślad nie niesie tokenu ani klucza. Wynika to z budowy: wpis czyta tylko nagłówki zapisane przez drzwi
   i ciało wysyłane do bramy.
4. Brak testu, że konfiguracja serwerów nie trafia do `.mcp.json` repozytorium. Wynika to z budowy: `claude-mcp.sh`
   pisze w zakresie użytkownika.
5. Nie zmierzone na prawdziwym tenancie: logowanie MSAL z nową rejestracją i cichy token dla drugiego API przez token
   odświeżania. Rejestracja powstaje dopiero przy `apply`; `mcp_token.py login` wypisuje role widziane w obu API i jest
   pierwszym pomiarem.

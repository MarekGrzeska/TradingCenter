# Tasks

Każda grupa zostawia repozytorium zielone i jest jednym commitem.

## 1. Moduł powstaje, kod się przenosi bez zmiany treści

- [ ] 1.1 `git mv modules/agent/agent modules/workbench/agent`, `modules/agent/migrations`
  → `modules/workbench/migrations/agent`, `modules/agent/tests` →
  `modules/workbench/tests/agent`
- [ ] 1.2 To samo dla `teams` → `modules/workbench/{teams,migrations/teams,tests/teams}`
- [ ] 1.3 `modules/teams-mcp/teams_mcp` → `modules/workbench/teams_tools`,
  `modules/teams-mcp/tests` → `modules/workbench/tests/teams_tools`
- [ ] 1.4 `modules/workbench/pyproject.toml` — suma zależności trzech modułów, cztery
  pakiety, konfiguracja ruff/pyright/pytest zebrana z trzech
- [ ] 1.5 `alembic-agent.ini`, `alembic-teams.ini` — dwa łańcuchy, dwa `script_location`
- [ ] 1.6 `Dockerfile` jeden, `uv.lock` jeden; `modules/{agent,teams,teams-mcp}` znikają

## 2. Jedno czytanie środowiska

- [ ] 2.1 `workbench/config.py` — jedyne miejsce czytające środowisko; buduje
  `agent.config.Settings` i `teams.config.Settings` argumentami
- [ ] 2.2 Przedrostki na tym, co zostaje podwójne: `AGENT_DATABASE_URL`,
  `TEAMS_DATABASE_URL`, `AGENT_OPENAI_API_KEY`, `TEAMS_OPENAI_API_KEY`, `AGENT_MODELS`,
  `TEAMS_MODELS`, `AGENT_DEFAULT_MODEL_ID`
- [ ] 2.3 `TEAMS_MCP_URL`, `TEAMS_MCP_SCOPE`, `TEAMS_MCP_REQUEST_TIMEOUT_SECONDS` out
- [ ] 2.4 `migrations/*/env.py` czytają URL swojej bazy z `workbench.config`
- [ ] 2.5 `.env.example` jeden, z powodem przy każdym przedrostku
- [ ] 2.6 Testy: konfiguracja nazywająca poświadczenie tylko jednej powierzchni jest
  odmową startu

## 3. Jedna aplikacja, dwa routery

- [ ] 3.1 `workbench/app.py` — jeden `lifespan`, dwie pule, dwa łańcuchy migracji pod
  własnymi kluczami blokady, oba `app.state` obok siebie
- [ ] 3.2 Zegar `teams` startuje i zatrzymuje się w tym samym `lifespan`
- [ ] 3.3 Kolizje: `/teams/models` i `/teams/usage`, zarejestrowane **przed** routerem
  katalogu; `/health` jedno
- [ ] 3.4 `agent/app.py` i `teams/app.py` znikają; conftesty obu drzew budują aplikację
  `workbench`
- [ ] 3.5 Test kolejności tras — literał wygrywa z `/teams/{team_id}`
- [ ] 3.6 `tests/test_layering.py` — statyczny czytnik importów, cztery reguły z D4

## 4. `teams-mcp` rozpuszcza się

- [ ] 4.1 `teams_tools/client.py` — `httpx.ASGITransport` na aplikacji `workbench`
  zamiast połączenia sieciowego; `teams_tools/config.py` i `server.py` out
- [ ] 4.2 `teams_tools/contract.py`, `contract/teams.openapi.json` i `test_contract.py` out
- [ ] 4.3 `agent/tools/registry.py` — trzecie źródło jest lokalne, nie sieciowe;
  `ToolServer(prefix="teams_mcp")` out
- [ ] 4.4 Token operatora jedzie do narzędzi tak jak jechał — testy autorstwa przenoszą się
  w całości
- [ ] 4.5 Testy: żaden serwer sieciowy nie odpowiada, a narzędzia zespołowe działają

## 5. CI, deploy, runner

- [ ] 5.1 `deploy-agent.yml` → `deploy-workbench.yml`; `deploy-teams.yml`,
  `deploy-teams-mcp.yml` out
- [ ] 5.2 `checks.yml` — trzy joby modułów → jeden, filtry ścieżek, macierz pakietów
- [ ] 5.3 `scripts/dev.py` — jeden wpis zamiast trzech, porty 8050 i 8070 out
- [ ] 5.4 `scripts/dev.py` mówi o `.env` sprzed tej zmiany, tak jak mówi o poprzednich

## 6. Infrastruktura

- [ ] 6.1 `azurerm_linux_web_app.teams`, `.teams_mcp`, `module.teams_easy_auth`,
  `module.teams_mcp_easy_auth`, dwa `data.azuread_service_principal`, dwa `output` out
- [ ] 6.2 App Service zostaje pod nazwą `app-tradingcenter-agent`, z komentarzem, że to
  decyzja (D2)
- [ ] 6.3 Ustawienia obu powierzchni na jednym App Service; `var.teams_models` zostaje
- [ ] 6.4 `static-web-app.tf` — jeden bazowy URL
- [ ] 6.5 **Operator, raz:** rola `app-tradingcenter-agent` w bazie `teams` z własnością
  schematu (`scripts/grant-schema-ownership.sql`)

## 7. Terminal

- [ ] 7.1 `VITE_TEAMS_HTTP` out, `VITE_AGENT_HTTP` → `VITE_WORKBENCH_HTTP`
- [ ] 7.2 `/teams/models` i `/teams/usage` w kliencie zespołów
- [ ] 7.3 `pnpm contract:generate` — generator czyta jedno źródło zamiast dwóch
- [ ] 7.4 `vite.config.ts` proxy, `.env.example`, `staticwebapp.config.json`

## 8. Dokumentacja

- [ ] 8.1 `CLAUDE.md` — mapa modułów, tabela komend, porty, pułapki `.env`, reguła warstw
- [ ] 8.2 `docs/architecture.md`, `README.md`, README modułu
- [ ] 8.3 `review.md` — przy scaleniu

# Tasks

Każda grupa jest jednym commitem. **Zielone jest repozytorium po grupie 3, nie po każdej** —
i to jest korekta planu, nie jego złamanie: grupy 1–3 dzielą jedną zmianę (przeniesienie,
konfiguracja, złożenie aplikacji), której nie da się rozciąć na trzy działające stany.
Grupa 4 wyszła z 3 tym samym commitem, bo rejestr narzędzi agenta i obiekt aplikacji, na
którym stoi transport ASGI, powstają w jednym miejscu.

Jedyna pozycja niezaznaczona jest operatora i jest nią z konstrukcji (6.5).

## 1. Moduł powstaje, kod się przenosi bez zmiany treści

- [x] 1.1 `git mv modules/agent/agent modules/workbench/agent`, `modules/agent/migrations`
  → `modules/workbench/migrations/agent`, `modules/agent/tests` →
  `modules/workbench/tests/agent`
- [x] 1.2 To samo dla `teams` → `modules/workbench/{teams,migrations/teams,tests/teams}`
- [x] 1.3 `modules/teams-mcp/teams_mcp` → `modules/workbench/teams_tools`,
  `modules/teams-mcp/tests` → `modules/workbench/tests/teams_tools`
- [x] 1.4 `modules/workbench/pyproject.toml` — suma zależności trzech modułów, cztery
  pakiety, konfiguracja ruff/pyright/pytest zebrana z trzech
- [x] 1.5 `alembic-agent.ini`, `alembic-teams.ini` — dwa łańcuchy, dwa `script_location`
- [x] 1.6 `Dockerfile` jeden, `uv.lock` jeden; `modules/{agent,teams,teams-mcp}` znikają

## 2. Jedno czytanie środowiska

- [x] 2.1 `workbench/config.py` — jedyne miejsce czytające środowisko; buduje
  `agent.config.Settings` i `teams.config.Settings` argumentami
- [x] 2.2 Przedrostki na tym, co zostaje podwójne: `AGENT_DATABASE_URL`,
  `TEAMS_DATABASE_URL`, `AGENT_OPENAI_API_KEY`, `TEAMS_OPENAI_API_KEY`, `AGENT_MODELS`,
  `TEAMS_MODELS`, `AGENT_DEFAULT_MODEL_ID`
- [x] 2.3 `TEAMS_MCP_URL`, `TEAMS_MCP_SCOPE`, `TEAMS_MCP_REQUEST_TIMEOUT_SECONDS` out
- [x] 2.4 `migrations/*/env.py` czytają URL swojej bazy z `workbench.config`
- [x] 2.5 `.env.example` jeden, z powodem przy każdym przedrostku
- [x] 2.6 Testy: konfiguracja nazywająca poświadczenie tylko jednej powierzchni jest
  odmową startu

## 3. Jedna aplikacja, dwa routery

- [x] 3.1 `workbench/app.py` — jeden `lifespan`, dwie pule, dwa łańcuchy migracji pod
  własnymi kluczami blokady, oba `app.state` obok siebie
- [x] 3.2 Zegar `teams` startuje i zatrzymuje się w tym samym `lifespan`
- [x] 3.3 Kolizje: `/teams/models` i `/teams/usage`, zarejestrowane **przed** routerem
  katalogu; `/health` jedno
- [x] 3.4 `agent/app.py` i `teams/app.py` znikają; conftesty obu drzew budują aplikację
  `workbench`
- [x] 3.5 Test kolejności tras — literał wygrywa z `/teams/{team_id}`
- [x] 3.6 `tests/test_layering.py` — statyczny czytnik importów, cztery reguły z D4

## 4. `teams-mcp` rozpuszcza się

- [x] 4.1 `teams_tools/client.py` — `httpx.ASGITransport` na aplikacji `workbench`
  zamiast połączenia sieciowego; `teams_tools/config.py` i `server.py` out
- [x] 4.2 `scripts/contract.py`, `contract/teams.openapi.json` i `test_contract.py` out
- [x] 4.3 `agent/tools/registry.py` — trzecie źródło jest lokalne, nie sieciowe;
  `ToolServer(prefix="teams_mcp")` out
- [x] 4.4 Token operatora jedzie do narzędzi tak jak jechał — testy autorstwa przenoszą się
  w całości
- [x] 4.5 Testy: żaden serwer sieciowy nie odpowiada, a narzędzia zespołowe działają

## 5. CI, deploy, runner

- [x] 5.1 `deploy-agent.yml` → `deploy-workbench.yml`; `deploy-teams.yml`,
  `deploy-teams-mcp.yml` out
- [x] 5.2 `checks.yml` — trzy joby modułów → jeden, filtry ścieżek, macierz pakietów
- [x] 5.3 `scripts/dev.py` — jeden wpis zamiast trzech, porty 8050 i 8070 out
- [x] 5.4 `scripts/dev.py` mówi o `.env` sprzed tej zmiany, tak jak mówi o poprzednich

## 6. Infrastruktura

- [x] 6.1 `azurerm_linux_web_app.teams`, `.teams_mcp`, `module.teams_easy_auth`,
  `module.teams_mcp_easy_auth`, dwa `data.azuread_service_principal`, dwa `output` out
- [x] 6.2 App Service zostaje pod nazwą `app-tradingcenter-agent`, z komentarzem, że to
  decyzja (D2)
- [x] 6.3 Ustawienia obu powierzchni na jednym App Service; `var.teams_models` zostaje
- [x] 6.4 Jeden bazowy URL dla terminala — w `deploy-terminal.yml`, nie w
  `static-web-app.tf`: ten plik nie nosi żadnego `VITE_*`, adresy jadą przez zmienne
  budowania
- [ ] 6.5 **Operator, raz:** rola `app-tradingcenter-agent` w bazie `teams` z własnością
  schematu (`scripts/grant-schema-ownership.sql`)

## 7. Terminal

- [x] 7.1 `VITE_TEAMS_HTTP` out, `VITE_AGENT_HTTP` → `VITE_WORKBENCH_HTTP`
- [x] 7.2 `/teams/models` i `/teams/usage` w kliencie zespołów
- [x] 7.3 `pnpm contract:generate` — źródeł nadal dwa (archiwum i powierzchnia zespołów),
  ale drugie czyta `modules/workbench`, a dokument opisuje samą tę powierzchnię: `/health`
  i trasy rozmowy z niego wypadły
- [x] 7.4 `vite.config.ts` — jeden wpis proxy `/workbench-api` zamiast dwóch;
  `.env.example`. Nie ma `staticwebapp.config.json` w tym module i nie było

## 8. Dokumentacja

- [x] 8.1 `CLAUDE.md` — mapa modułów, tabela komend, porty, pułapki `.env`, reguła warstw
- [x] 8.2 `docs/architecture.md`, `README.md`, README modułu
- [x] 8.3 `review.md`

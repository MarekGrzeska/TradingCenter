## 1. Entra i wdrożenie

- [x] 1.1 `infra/entra.tf`: rejestracja `app-tradingcenter-claude-code` (klient publiczny), service principal, pre-autoryzacje na API workbencha i bramy, output `claude_code_entra_client_id`
- [x] 1.2 `deploy/env.required`, `deploy/scripts/fill-github-environment.sh`: `CLAUDE_CODE_APPLICATION_ID`
- [x] 1.3 `deploy/Caddyfile`: `API_HOST` niesie `/…/mcp` i `/trading/*` → trading-mcp; `GATEWAY_HOST` dalej 404
- [x] 1.4 `deploy/docker-compose.yml`: listy wołających narzędzi, trading-mcp w sieci `edge` z tenantem, audiencją bramy i listą zewnętrznych wołających
- [x] 1.5 `scripts/tests/test_deploy_compose.py` dostosowane do nowej krawędzi

## 2. tc-entra-auth

- [x] 2.1 `EdgeConfig.token_applications`: token od aplikacji spoza listy → 403 przed rolą; testy w pakiecie

## 3. trading-mcp

- [x] 3.1 Ustawienia: tenant, audiencje, lista zewnętrznych wołających; odmowa startu przy liście bez tenanta/audiencji
- [x] 3.2 `edge_config`: weryfikator, `RolePolicy` i `token_applications`, gdy lista niepusta; pusta = jak dziś
- [x] 3.3 Ślad zapisu w logu przed wysłaniem i ze skutkiem, z aplikacją i osobą
- [x] 3.4 Testy drzwi (admin z listy, aplikacja spoza listy, viewer, zła audiencja) i śladu

## 4. Workbench

- [x] 4.1 Strategie: `/strategies/mcp` zamontowane, rekord z `tools_prefix`, lista wołających narzędzi, sesja w `serving`
- [x] 4.2 Narzędzia zespołów: serwer sieciowy ustawiający osobę z żądania, montaż `/team-tools` z rekordem i listą
- [x] 4.3 `workbench/config.py`: lista wołających narzędzi trafia też do strategii i narzędzi zespołów
- [x] 4.4 Testy: jedna droga przez drzwi na `/market/mcp`, strategie pod `/mcp`, osoba z żądania dociera do narzędzia zespołu

## 5. Po stronie operatora i dokumentacja

- [x] 5.1 `scripts/mcp_token.py` (`login`, `headers`) i `scripts/claude-mcp.sh` (`install`, `remove`)
- [x] 5.2 CLAUDE.md, `deploy/README.md`, `docs/architecture.md`, README pakietów i trading-mcp
- [x] 5.3 Testy, ruff i pyright w zmienionych modułach i pakietach; `openspec validate --strict`
- [x] 5.4 Raport `docs/operator-mcp-access.html`

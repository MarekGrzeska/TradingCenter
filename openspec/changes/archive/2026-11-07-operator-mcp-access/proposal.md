## Why

Narzędzia systemu — archiwa, Telegram, alerty, strategie, zespoły i rachunek demo — są dziś osiągalne wyłącznie z rozmowy
w terminalu. Operator pracuje też w Claude Code i chce sięgać po te same narzędzia produkcji stamtąd, bez otwierania
terminala. Decyzja D7 zmiany `a-strategy-from-a-description` („operator nie ma klienta MCP”) przestała być prawdą: ma go.

## What Changes

- Sześć powierzchni narzędziowych workbencha (`/market`, `/polymarket`, `/social`, `/telegram`, `/youtube`, `/alerts`),
  które już stoją pod `/…/mcp`, krawędź zaczyna przepuszczać na hoście API; brama dalej ich nie niesie.
- Strategie dostają zamontowane `/strategies/mcp` (dziś zbudowany serwer bez transportu), a narzędzia zespołów —
  sieciową powierzchnię `/team-tools/mcp`, działającą w imieniu osoby z tokenu.
- trading-mcp staje się osiągalny z zewnątrz pod `https://<API_HOST>/trading/mcp`: token Entra wydany dla API bramy,
  rola `admin` i aplikacja z wyliczonej listy. Droga workbencha (klucz w sieci wewnętrznej) zostaje bez zmian.
- Wywołanie zapisujące z zewnątrz zostawia w trading-mcp ślad w logu przed wysłaniem i po skutku.
- Nowa rejestracja Entra `app-tradingcenter-claude-code` (klient publiczny), pre-autoryzowana na API workbencha i bramy;
  jej identyfikator jest jedynym wpisem list wołających narzędzi.
- `scripts/mcp_token.py` (helper `headersHelper` Claude Code: logowanie raz, potem token po cichu) i
  `scripts/claude-mcp.sh` (rejestracja serwerów w zakresie użytkownika Claude Code).
- `tc-entra-auth`: `EdgeConfig` umie ograniczyć wołających z tokenem do wyliczonej listy aplikacji.

Bez zmian: rola `viewer` nie sięga żadnego `/mcp`; narzędzia rozmowy (wykres, rysunki) nie wychodzą na zewnątrz; nic nie
jest wdrażane ani mergowane w ramach tej zmiany — `terraform apply` i zmienna środowiska GitHub są krokami operatora.

## Capabilities

### New Capabilities
- `operator-tool-access`: kto i jak sięga po powierzchnie narzędziowe produkcji spoza systemu — krawędź, token, rola,
  wyliczona aplikacja, helper tokenu po stronie operatora.

### Modified Capabilities
- `trading-mcp-transport`: lista wołających ma dwie pozycje (workbench kluczem, aplikacja operatora tokenem); zapis od
  wołającego z tokenem zostawia ślad w logu.
- `strategies-tools`: narzędzia strategii są też serwowane pod `/strategies/mcp` wołającym z listy narzędziowej
  (dalej nie trafiają do zespołów ani alertów).
- `workbench-team-tools`: zestaw jest osiągalny przez sieć i bierze tożsamość operatora z tokenu wołającego.

## Impact

- `deploy/Caddyfile`, `deploy/docker-compose.yml`, `deploy/env.required`, `deploy/scripts/fill-github-environment.sh`,
  `scripts/tests/test_deploy_compose.py`.
- `infra/entra.tf` (+ output) — `apply` przed merge, inaczej deploy zatrzyma się na brakującym `CLAUDE_CODE_APPLICATION_ID`.
- `packages/tc-entra-auth` (pole `token_applications`), `modules/trading-mcp` (config, `edge_config`, ślad zapisów),
  `modules/workbench` (strategie, nowy montaż narzędzi zespołów, konfiguracja list wołających).
- CLAUDE.md (wiersz trading-mcp, pułapka krawędzi), `deploy/README.md`, `docs/architecture.md`.
- `review.md` powstaje po implementacji; wszystkie artefakty są pisane.

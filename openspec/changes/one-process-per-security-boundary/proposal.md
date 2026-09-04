## Why

Pomiar z 4 września 2026 (`docs`: „Droga na B2", „Trzy procesy zamiast ośmiu") zmienił jedną
liczbę, na której stała decyzja z 20 sierpnia o niezwijaniu modułów. Każda aplikacja App Service
kosztuje ~230 MB pamięci, zanim uruchomi choć linię Pythona: log platformy z Kudu pokazuje, że przy
każdej z ośmiu aplikacji startują kontener tożsamości zarządzanej (`StartingMsiContainer`) i kontener
Easy Auth (`StartingAuthContainer`), a ten sam obraz gatewaya pod realnym strumieniem Capital waży
w Dockerze 76 MB wobec 372–471 MB raportowanych w App Service. Osiem procesów to ~1,3 GB
sidecarów, których nie zdejmie żadna zmiana w kodzie, plus 2,3 GB narzutu planu poza aplikacjami.
Plan B2 (3 584 MB, 22,6 EUR zamiast 45,2) jest z ośmioma procesami nieosiągalny; z trzema albo
czterema może być, i tylko przez mniejszą liczbę procesów.

`docs/mniej-modulow-czy-aks.html` odrzucił sklejanie z dwóch powodów: pamięci było w bród
(„miejsce na ~20 kolejnych modułów"), a oszczędność była obudową, po którą istnieje `packages/`.
Pierwszy powód upadł z pomiaru. Drugi jest prawdziwy i stoi w tej propozycji w kolumnie „przeciw".
Reguła z tamtego dokumentu — **zwija się to, co stoi przed właścicielem swoich danych; nie zwija się
tego, co stoi przed inną granicą bezpieczeństwa** — zostaje i wyznacza cel.

## What Changes

- **BREAKING dla CLAUDE.md — reguła nośna zmienia brzmienie.** „No module imports another module"
  staje się: **jeden proces na granicę bezpieczeństwa; wewnątrz procesu pakiety, z których żaden
  nie importuje sąsiada, i jedno miejsce składania, które importuje wszystkie — pilnowane testem
  czytającym importy z AST.** To jest reguła, którą workbench ma od 19 sierpnia jako „drugą formę";
  ta zmiana czyni ją pierwszą. Warunek „trzecia droga tylko przy jednej tożsamości i jednym
  operatorze" z 20 sierpnia zostaje odwrócony na piśmie: powierzchnie o różnych regułach zapisu
  rozróżnia rekord tras w procesie (`caller_access`), tak jak w market-data od 19 sierpnia.
- **Trzy granice bezpieczeństwa, trzy procesy.** `capital-gateway` (jedyne drzwi do dostawcy,
  `/ws/stream` broniony samym kluczem) i `trading-mcp` (jedyny proces, który rusza rachunek, z
  osobną tożsamością na osobnej liście) zostają modułami-procesami bez zmian. Pozostałe moduły —
  `market-data`, `polymarket-data`, `social-data`, `strategy`, warunkowo `telegram-gateway` — stają
  się pakietami jednego procesu, którym jest dzisiejszy `workbench` (App Service
  `app-tradingcenter-agent`, ta sama tożsamość). Decyzja `zwiniecie-trading-mcp` z 20 sierpnia stoi.
- **Każdy pakiet montuje się jako pod-aplikacja pod przedrostkiem** (`/polymarket`, `/social`,
  `/strategy`, `/market`, warunkowo `/telegram`); `agent` zostaje na korzeniu, `teams` pod `/teams`
  jak dziś. Własny `/openapi.json`, własny `/mcp`, własne middleware i rekord tras każdego pakietu
  zostają przy nim. **BREAKING dla terminala i pocketu:** pięć bazowych adresów i pięć scope'ów
  Entra staje się jednym adresem z przedrostkami i jednym scope'em obok bramy.
- **Narzędzia czterech serwerów MCP stają się źródłami w procesie** w obu rejestrach workbencha
  (wzór `LocalTeamsTools`): te same nazwy, opisy, sufity i odmowy; cztery pary `*_MCP_URL`/`_SCOPE`
  znikają. `TRADING_MCP_URL` zostaje, bo trading-mcp zostaje.
- **Sześć baz zostaje sześcioma bazami**: sześć łańcuchów migracji pod sześcioma kluczami blokady w
  jednym `lifespan`, sześć pul o sumie pilnowanej jednym testem. Scalanie danych nie jest tą decyzją.
- **BREAKING dla środowiska:** to, co istnieje wielokrotnie, dostaje przedrostek pakietu
  (`MARKET_`, `POLYMARKET_`, `SOCIAL_`, `STRATEGY_` obok `AGENT_`/`TEAMS_`); reszta jest jedna.
- **Etapowo, z bramką po każdym etapie i działającą produkcją między nimi**: 0 decyzja i pomiar
  sidecara Auth · 1 szkielet · 2 trzy pętle · 3 market-data i godzina na B2 · 4 warunkowo telegram ·
  5 B2 w Terraformie. Szczegóły i liczby: `design.md`; kroki: `tasks.md`.

## Capabilities

Ta zmiana nie zmienia żadnego wymagania: to, co każdy moduł MUSI, zostaje co do słowa, zmienia się
granica procesu, w którym to robi. `skip_specs: true` w `.openspec.yaml` z tego powodu. Adresy, które
przenoszą się pod przedrostek, nie są w żadnej specyfikacji wymaganiem (`grep` po `openspec/specs`
nie znajduje ścieżek `/mcp`, `/ws/candles`, `/health`); jeśli etap 2 lub 3 dotknie specyfikacji
`terminal-*` w miejscu, gdzie nazywa bazowy adres, dostanie własną deltę w osobnej zmianie tego etapu.

### New Capabilities

—

### Modified Capabilities

—

## Impact

- **Kod:** `modules/polymarket-data`, `modules/social-data`, `modules/strategy`, `modules/market-data`
  (i warunkowo `modules/telegram-gateway`) przenoszą się jako pakiety do `modules/workbench`;
  `workbench/app.py` składa je; `tests/test_layering.py` pilnuje N pakietów zamiast trzech;
  `strategy/archive.py` znika na rzecz wstrzykniętego protokołu; wskaźniki market-data liczone
  w `asyncio.to_thread`.
- **Infra:** cztery–pięć `azurerm_linux_web_app` mniej, ich reguły firewalla, tożsamości, rejestracje
  Entra terminala i pocketu, dotacje Key Vault; listy wołających przy bramie i trading-mcp dostają
  tożsamość workbencha; alerty i web test wskazują workbench. `sku_name = "B2"` dopiero w etapie 5,
  po pomiarze.
- **Operator, raz na bazę:** `scripts/grant-schema-ownership.sql` dla roli `app-tradingcenter-agent`
  na `market`, `polymarket`, `social`, `strategy` (i `telegram`) — dokładnie jak 19 sierpnia dla `teams`.
- **CI/deploy:** pięć jobów i pięć workflowów deploy mniej; `changes` w `checks.yml` czyta nową mapę.
- **Terminal, pocket:** jeden bazowy adres z przedrostkami, jeden scope; kontrakty generowane bez zmian
  poza adresem.
- **Dokumenty:** CLAUDE.md (reguła, tabela modułów, porty), `docs/architecture.md` (diagram, „What may
  be shared"), `docs/mniej-modulow-czy-aks.html` do archiwum z notą, pięć przewodników → jeden.
- **Koszt i zysk:** ~1,5–2 tygodnie pracy; −5 par sidecarów (≈ −1 150 MB), −5 App Service, −4
  rejestracje Entra, −5 workflowów, ~−830 linii Terraforma; 22,6 EUR miesięcznie **tylko jeśli** godzina
  testu na B2 po etapie 3 pokaże plan poniżej 85%. Bez tego zysk jest operacyjny, nie pieniężny, i tak
  jest tu nazwany.
- **Skipped:** żadnego z artefaktów nie pomija się; `review.md` po etapie 5 albo po tym etapie, na
  którym plan stanął z zapisanym powodem.

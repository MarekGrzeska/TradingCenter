## Why

`agent` i `teams` to dwa procesy, których treść jest tą samą treścią. Pętla tury modelu jest
strukturalnie jedna — mówią to oba docstringi — a `agent` jest zespołem-jedynką z SSE
i wykresem. Cena rozdzielenia jest policzalna i policzona na `main @ c49b658`:

- **bliźniaki**, których pakiet nie umiał objąć, bo różnią się typem, nie zachowaniem:
  `tools/client.py` (508 wobec 488 linii), rejestr serwerów narzędzi, `provider.py`,
  `models_catalogue.py`, `routers/models.py` (identyczne co do znaku poza importem),
  `auth.py`, `runtime.py`, `migrations/env.py`, `conftest.py`'s `_no_developer_env`;
- **15 z 19 zmiennych środowiskowych istnieje podwójnie** — `DATABASE_USER`, trójka
  `AZURE_*`, po trzy ustawienia `MARKET_MCP_*` i `TRADING_MCP_*`,
  `REQUIRE_AUTHENTICATED_PRINCIPAL`, `LOG_LEVEL`;
- **`teams-mcp` istnieje wyłącznie dlatego, że `agent` buduje zespoły u sąsiada przez
  sieć**: 1 428 linii pakietu, 1 866 linii testów i skryptu, 3 047 linii migawki cudzego
  OpenAPI, App Service, Dockerfile, lock, workflow deploy, triplet Entra, port 8070.
  Jego jedyny wołający i jego cel byłyby w jednym procesie.

To kierunek B z `docs/rachunek-po-refactorze.html` — „największy pojedynczy zysk na stole",
i pierwsza jego faza: **wspólny proces, dwa routery, dwa schematy**. Scalanie pętli tury nie
wchodzi tą zmianą i może nie wejść nigdy.

Kolejność w rachunku brzmiała A(teams) → B. Ta zmiana **pomija A(teams) i to jest jej
oszczędność, nie skrót**: A(teams) wmontowałoby `teams-mcp` w `teams` jako trasę `/mcp`,
żeby chwilę później B usunęło ostatni powód, dla którego ta trasa jest po sieci. Wykonanie
obu znaczy przenieść ten sam kod dwa razy. Cena pominięcia: nie ma drugiego udanego A przed
B, czyli B rusza z jednym dowodem wzorca zamiast dwóch.

## What Changes

- **Powstaje `modules/workbench`** — jeden moduł, jeden proces, jeden obraz, jedno App
  Service. `modules/agent`, `modules/teams` i `modules/teams-mcp` przestają istnieć.
- **Dwa pakiety w jednym procesie.** `workbench/agent/` i `workbench/teams/` zostają
  osobnymi pakietami z osobnymi routerami; `workbench/app.py` jest jedynym miejscem, gdzie
  powstaje aplikacja FastAPI, i jedynym, które czyta środowisko.
- **Dwa schematy bazy zostają** — `agent` i `teams` to nadal dwie bazy, dwa łańcuchy
  migracji i dwa klucze blokady doradczej, migrowane w jednym `lifespan`, każdy pod swoim
  kluczem. Scalanie danych to osobna decyzja i ta zmiana jej nie podejmuje.
- **Dwa klucze OpenAI zostają** — rozdział kosztu eksperymentów to dwa klienty w jednym
  procesie, nie granica modułu. Tak samo dwa katalogi modeli.
- **BREAKING — `teams-mcp` rozpuszcza się w wywołanie funkcji.** Narzędzia zespołowe
  zostają co do nazwy, opisu, sufitu i kształtu odmowy; znika transport sieciowy między
  nimi a `teams`, migawka kontraktu i skrypt jej pilnujący — schemat w tym samym procesie
  nie ma jak być nieświeży. Wywołanie narzędzia zespołowego: 2 hopy → 0.
- **BREAKING — kolizje tras.** `GET /models` i `GET /usage` istnieją dziś w obu modułach
  z różnym kształtem odpowiedzi. Powierzchnia `agent` zostaje na korzeniu bez zmian;
  odpowiedniki `teams` przenoszą się na **`/teams/models`** i **`/teams/usage`**. Każda
  inna trasa obu modułów zostaje dokładnie tam, gdzie była.
- **BREAKING — zmienne środowiskowe.** To, co zostaje podwójne, dostaje przedrostek:
  `AGENT_DATABASE_URL`/`TEAMS_DATABASE_URL`, `AGENT_OPENAI_API_KEY`/`TEAMS_OPENAI_API_KEY`,
  `AGENT_MODELS`/`TEAMS_MODELS`, `AGENT_DEFAULT_MODEL_ID`. Reszta jest jedna.
  `TEAMS_MCP_URL`, `TEAMS_MCP_SCOPE` i `TEAMS_MCP_REQUEST_TIMEOUT_SECONDS` znikają.
- **Terminal traci jeden bazowy URL** — `VITE_TEAMS_HTTP` znika, `VITE_AGENT_HTTP` staje
  się `VITE_WORKBENCH_HTTP`.
- **Nazwa App Service nie zmienia się** i to jest decyzja, nie przeoczenie —
  `app-tradingcenter-agent` zostaje. Uzasadnienie w `design.md`, D2.

## Capabilities

### New Capabilities

- `workbench-process`: co znaczy „jeden proces, dwa schematy" — czego moduł dowodzi przy
  starcie, co robi, gdy jedna z dwóch baz nie odpowiada, i którą powierzchnię obsługuje pod
  którą ścieżką.
- `workbench-team-tools`: narzędzia zespołowe jako warstwa w procesie — w czyim imieniu
  powstaje zespół, przebieg i harmonogram założony rozmową z modelem, i co się dzieje, gdy
  tożsamości operatora nie da się ustalić.

### Modified Capabilities

- `agent-tool-access`: serwerów narzędzi po sieci jest dwa, nie trzy, a trzecie źródło
  narzędzi jest w tym samym procesie. Wymaganie o niezależności serwerów zostaje i obejmuje
  źródło lokalne; wymaganie „moduł nie trzyma kopii tego, co ogłasza serwer" przestaje
  dotyczyć narzędzi zespołowych, bo nie ma dwóch kopii do rozjechania.
- `teams-mcp-tools`: usunięte w całości — wymagania przenoszą się do
  `workbench-team-tools` bez zmiany treści.
- `teams-mcp-authorship`: usunięte w całości — wymagania przenoszą się do
  `workbench-team-tools`. Jedno zmienia treść: „maszyna deweloperska, gdzie nikt nie może
  być uwierzytelniony" przestaje zależeć od tego, czy `teams` jest wołane w pętli zwrotnej,
  bo nie jest wołane wcale.
- `teams-mcp-transport`: usunięte w całości. „Jeden transport" i „jeden nazwany wołający"
  tracą przedmiot, gdy nie ma procesu do wołania; „jedno wejście bez poświadczenia"
  przenosi się do `workbench-process`.
- `teams-mcp-upstream-access`: usunięte w całości. Cztery wymagania opisują połączenie,
  którego nie ma; w tym „kontrakt modułu `teams` jest sprawdzany, nie zakładany" — ta
  zmiana usuwa powód, dla którego istniał.

## Impact

**Kod.** `modules/workbench/` z `agent/` (5 422 linie), `teams/` (7 017) i `teams_tools/`
(z `teams_mcp/`, ~1 300 po odjęciu klienta HTTP i jego konfiguracji) obok siebie; testy
łączą się w jedno drzewo (6 889 + 7 604 + ~1 700). Znika: `teams_mcp/client.py`,
`teams_mcp/config.py`, `teams_mcp/server.py`, `scripts/contract.py`, migawka
`contract/teams.openapi.json`, `agent/tools/client.py`'s tryb `teams_mcp`, jeden
`provider.py`, jeden `models_catalogue.py`, jeden `routers/models.py`, jeden `auth.py`.

**Konsumenci.** `terminal` — jeden bazowy URL i dwie ścieżki (`/teams/models`,
`/teams/usage`). `market-data` i `trading-mcp` — bez zmian, bo tożsamość wołającego jest ta
sama (patrz D2). `capital-gateway` — bez zmian.

**Infrastruktura.** Ubywa `azurerm_linux_web_app.teams`, `azurerm_linux_web_app.teams_mcp`,
`module.teams_easy_auth`, `module.teams_mcp_easy_auth`, dwa
`data.azuread_service_principal`, dwa `output`. Zostaje jedno App Service pod dotychczasową
nazwą, z ustawieniami obu modułów. `terraform apply` jest operatora — a ta zmiana rusza
`azuread_*`, więc jest jego z konstrukcji.

**Baza.** Dwie bazy zostają. Rola `app-tradingcenter-agent` musi powstać w bazie `teams`
i przejąć własność jej schematu (`scripts/grant-schema-ownership.sql`) — jednorazowy krok
operatora, ten sam, który każda baza tego repozytorium przeszła raz. To jedyny krok
operatorski tej zmiany po stronie danych i jest opisany w `tasks.md`.

**CI i narzędzia.** `deploy-teams.yml` i `deploy-teams-mcp.yml` znikają,
`deploy-agent.yml` staje się `deploy-workbench.yml`. Joby w `checks.yml`: 12 → 10.
`scripts/dev.py` traci dwa wpisy i dwa porty (8050, 8070); zostaje 8030.

**Dokumentacja.** `CLAUDE.md` (mapa modułów, tabela komend, porty, pułapki `.env`),
`docs/architecture.md`, `README.md`, README modułów.

**Czego ta zmiana nie rusza.** Pętli tury modelu — `agent/turn.py` i `teams/runner/loop.py`
zostają osobne i nietknięte. Kontraktu `market-data`, granicy do capital.com,
`trading-mcp`. Reguła „no module imports another module" zostaje w literze: nie powstaje
żaden nowy import **między modułami** — dwa moduły przestają istnieć osobno. W zamian
powstaje reguła warstw wewnątrz procesu, zapisana w `design.md` D4.

**Czego nie ma w tej zmianie.** `review.md` powstaje na końcu, przy scaleniu — zmiana jest
ryzykowna i weryfikacja nie wynika z samych testów.

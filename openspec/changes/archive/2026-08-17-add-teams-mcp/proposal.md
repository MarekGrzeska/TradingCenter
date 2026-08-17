## Why

Zespół powstaje dziś wyłącznie ręką: operator przeciąga pudełka po kanwie, wpisuje prompt
każdej roli, wybiera model i narzędzia, zapisuje rewizję. To jest dobre, kiedy wiadomo, co
się chce zbudować, i kosztowne, kiedy się dopiero szuka — a szukanie jest normalnym stanem
tej pracy. Zdanie „zrób zespół, który rano czyta wybicia na US100 i mówi, czy warto wchodzić"
niesie tyle samo informacji co dziesięć minut klikania.

Drugi powód jest ostrzejszy i dotyczy poprawiania, nie zakładania. Przebieg zostawia ślad:
kto co powiedział, ile to kosztowało, które narzędzie odpowiedziało czym. Wniosek z tego
śladu — „ten agent dostaje za mało kontekstu", „ta rola jest zbędna" — trzeba dziś przenieść
ręką do drugiej zakładki i przepisać na formularz. Model, który przed chwilą ten ślad czytał,
mógłby po prostu zapisać poprawioną rewizję.

Moduł `agent` jest już w oknie czatu, zna rynek przez narzędzia `market-mcp` i zna tożsamość
operatora, który do niego pisze. Brakuje mu wyłącznie drogi do katalogu zespołów.

## What Changes

- **Nowy moduł `modules/teams-mcp`** — siódmy, serwer MCP nad HTTP-owym API `teams`, tą samą
  drogą co `market-mcp` nad `market-data` i `trading-mcp` nad gatewayem. Jeden nazwany
  wołający: `agent`.
- **Zredukowany katalog narzędzi**, nie odwzorowanie 36 tras `teams` jeden do jednego.
  Narzędzia mówią językiem zadania operatora — „załóż zespół", „popraw rolę", „uruchom",
  „pokaż, co wyszło" — a nie językiem tras HTTP.
- **Zespół założony z czatu należy do operatora**, nie do modułu. Tożsamość operatora
  przechodzi cały łańcuch terminal → `agent` → `teams-mcp` → `teams`, więc zespół pojawia
  się w zakładce Teams w terminalu, a jego przebiegi na liście przebiegów tego samego
  człowieka. Mechanizm przenoszenia tożsamości rozstrzyga `design.md` — jest to
  najważniejsza decyzja tej zmiany i ma nazwane alternatywy.
- **Pierwsze narzędzia zapisujące, jakie dostaje `agent`.** Dotąd czytał archiwum i rysował
  we własnej bazie. Teraz zakłada i zmienia cudze wiersze — w module, który wydaje pieniądze.
- **Model działa bez potwierdzeń, a chronią granice, które `teams` już ma** — dobowa granica
  kosztu zespołu i granice handlowe. Decyzja operatora, świadoma; `design.md` nazywa jej
  konsekwencje, w tym tę, że granica dobowa jest liczona **na zespół**, więc model zakładający
  nowy zespół zaczyna z czystym budżetem.
- **Pełna powierzchnia od razu, z harmonogramami i wyzwalaczami.** Zegar na produkcji jest
  wyłączony do czasu ręcznego przebiegu, więc harmonogram założony z czatu poczeka na
  włączenie — narzędzie ma to mówić wprost, zamiast milczeć.
- **`agent` uczy się więcej niż jednego serwera narzędzi.** Dziś ma dokładnie jeden
  (`market_mcp_url`). Kształt rejestru przenosimy z `teams`, kopiowany, nie współdzielony.
- Brak `TEAMS_MCP_URL` zostaje **stanem wspieranym**: agent bez niego działa jak dziś, bez
  narzędzi do zespołów.

## Capabilities

### New Capabilities
- `teams-mcp-tools`: co zestaw narzędzi potrafi i czego świadomie nie potrafi — katalog
  zredukowany do zadań operatora, opis narzędzia jako część kontraktu, narzędzia zapisujące
  oznaczone jako zmieniające stan
- `teams-mcp-authorship`: w czyim imieniu powstaje zespół, przebieg i harmonogram — tożsamość
  operatora niesiona przez łańcuch, i co się dzieje, gdy jej nie ma
- `teams-mcp-upstream-access`: jak moduł rozmawia z `teams` — tryb połączenia wybrany
  jednoznacznie, migawka kontraktu sprawdzana zamiast zakładanej, skończony czas wołania
- `teams-mcp-transport`: jak moduł jest osiągalny i przez kogo — jeden transport, jeden
  nazwany wołający, `/health` bez poświadczenia

### Modified Capabilities
- `agent-tool-access`: „Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie" i
  „Brak serwera narzędzi nie odbiera agentowi mowy" przestają mówić o **jednym** serwerze —
  agent ma ich teraz kilka, konfigurowanych i nieosiągalnych niezależnie od siebie

## Impact

- **Nowy moduł**: `modules/teams-mcp/` — port **8070**, własny `pyproject.toml`, testy,
  README, migawka kontraktu `teams` (`scripts/contract.py check`, wzorem obu istniejących
  serwerów MCP).
- **`modules/agent`**: rejestr serwerów narzędzi zamiast jednego, nowe ustawienia
  `TEAMS_MCP_URL` / `TEAMS_MCP_SCOPE` / `TEAMS_MCP_REQUEST_TIMEOUT_SECONDS`, prompt, który
  wie, że te narzędzia istnieją.
- **`modules/teams`**: prawdopodobnie zmiana po stronie przyjmowania tożsamości wołającego
  usługowego — zależy od mechanizmu wybranego w `design.md`. Jeśli okaże się potrzebna,
  delta trafia do tej zmiany.
- **Infrastruktura**: App Service, tożsamość zarządzana, Easy Auth z jednym wołającym,
  wpis `teams-mcp` w `allowed_applications` po stronie `teams`, adres w ustawieniach `agent`.
- **Pojemność**: plan `asp-tradingcenter` to B2, jeden worker, sześć aplikacji, pamięć po
  wdrożeniu z 16 sierpnia **84%** przy progu alertu 92%. Zmiana `scale-app-service-plan-to-b2`
  policzyła koszt lokatora na 150–310 MB. Siódma aplikacja to pytanie o SKU, nie formalność —
  `design.md` musi na nie odpowiedzieć, zanim ktokolwiek zacznie ją wdrażać.
- **CI i wdrożenie**: `checks.yml` (job modułu plus wciągnięcie go przy zmianie
  `teams/contract.py`), `deploy-teams-mcp.yml` ze smoke checkiem sięgającym procesu,
  `scripts/dev.sh` i `dev.ps1`.
- **Dokumentacja**: `CLAUDE.md`, `README.md`, `docs/architecture.md` — mapa modułów rośnie
  o jeden i o jedną krawędź.

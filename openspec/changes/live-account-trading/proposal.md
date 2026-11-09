## Why

Strategie z rodziny „pierwsza świeca M5 sesji USA” mają za sobą backtesty i demo, a system umie handlować wyłącznie
na koncie demonstracyjnym — blokada siedzi w trzech miejscach (host w `capital-gateway`, pytanie `trading-mcp` przed
otwarciem portu, wymagania `capital-session`, `capital-trading`, `trading-mcp-upstream-access`). Operator chce składać
zlecenia na koncie realnym capital.com obok demo, nie zamiast niego. Dwie specyfikacje (`agent-trading`,
`teams-trading`) uzasadniają brak granic handlowych tym, że „ochroną jest konto demo” — przy koncie realnym to
uzasadnienie przestaje działać i musi je zastąpić granica egzekwowana u jedynych drzwi do dostawcy.

## What Changes

- Druga instancja `capital-gateway` w trybie **konta realnego**, wybranym jawnym ustawieniem, a nie wywnioskowanym z
  adresu: tylko na serwerze, tylko dokładny host realny, tylko jedno wskazane konto, tylko rachunek i wykonanie (bez
  katalogu, historii, strumienia, zasilenia i przełączania konta). Bez skonfigurowanych granic nie wstaje.
- Granice konta realnego w tej bramie: lista dozwolonych instrumentów i największa wielkość jednego zlecenia na
  instrument. Zlecenie poza nimi jest odmową przed wysłaniem do dostawcy; zamknięcie pozycji, zmiana stopów i
  anulowanie zlecenia oczekującego są zawsze dozwolone. Każdy zapis zostawia ślad w logu bramy, przed i po.
- Druga instancja `trading-mcp`, która przed otwarciem portu sprawdza u swojej bramy, że ta jest na koncie realnym — i
  odwrotnie: instancja demo nadal odmawia startu przy bramie innej niż demo. Instancja realna nie wystawia zasilenia
  ani przełączania konta, a jej instrukcje i opisy narzędzi mówią wprost, że to pieniądze.
- Kto może handlować na koncie realnym: Claude Code operatora (`/trading-live/mcp`), agent na Telegramie (osobny
  przełącznik, domyślnie wyłączony) i **zespoły** — rewizja zespołu wybiera środowisko obok konta. **Rozmowa w
  terminalu nie sięga konta realnego** w żadnej konfiguracji.
- Terminal pokazuje konto realne osobno od kont demo (saldo, pozycje, zlecenia oczekujące) i ma jeden zapis:
  awaryjne „zamknij wszystko” — wszystkie pozycje i zlecenia oczekujące konta realnego, z potwierdzeniem.
- Wdrożenie: instancje realne startują tylko, gdy operator je włączy; bez tego serwer wygląda i działa jak dziś.
  Nowe sekrety w środowisku `vps`. Bez zmian w Entra (`infra/`): ta sama publiczność API bramy i rola `admin`.
- **BREAKING** w kontrakcie zespołów: `trading.environment` (`demo` | `live`, domyślnie `demo`) w definicji rewizji;
  istniejące rewizje czytają się jak dotąd.

Poza zakresem: dzienna granica straty, łączna ekspozycja i liczba pozycji, zatwierdzanie zleceń w terminalu albo
Telegramie — każde z nich to osobna zmiana, gdy pierwsze tygodnie na realnym pokażą potrzebę.

## Capabilities

### New Capabilities
- `capital-live-account`: brama w trybie konta realnego — warunki startu, jedno konto, granice zleceń, zawężone
  trasy, ślad zapisów i awaryjne zamknięcie wszystkiego.

### Modified Capabilities
- `capital-session`: środowisko jest jawnym wyborem z domyślnym demo, zamiast „wyłącznie demo”.
- `capital-trading`: handel na koncie realnym osiągalny tylko w procesie konta realnego.
- `trading-mcp-upstream-access`: moduł pracuje na środowisku, dla którego go uruchomiono, potwierdzonym przez bramę.
- `trading-mcp-tools`: zestaw nazywa środowisko; na koncie realnym bez zasilenia i przełączania konta.
- `agent-trading`: rozmowa nie sięga konta realnego.
- `teams-trading`: rewizja wybiera środowisko; zespół na koncie realnym musi nazwać konto.
- `terminal-accounts`: konto realne na ekranie rachunku i awaryjne zamknięcie wszystkiego.
- `claude-agent-access` (z otwartej zmiany `operator-agent-on-telegram`): zapis na koncie realnym ma własny przełącznik.

## Impact

- Kod: `modules/capital-gateway` (ustawienia, trasy, granice, ślad), `modules/trading-mcp` (oczekiwane środowisko,
  zawężony zestaw), `modules/workbench/teams` (środowisko w rewizji, drugi serwer narzędzi), `modules/terminal`
  (sekcja konta realnego), `modules/claude-agent` (drugi serwer i przełącznik), `scripts/claude-mcp.sh`.
- Kontrakty: definicja rewizji zespołu (wygenerowany kontrakt terminala, `contract-sync`), migawka OpenAPI bramy w
  `trading-mcp` (nowa trasa zamknięcia wszystkiego).
- Wdrożenie: `deploy/docker-compose.yml` (dwie usługi w profilu `live`, osobne sieci), `Caddyfile`
  (`/trading-live/*` na hoście API, `/live/*` na hoście bramy), `deploy/env.required`, sekrety `vps`.
- Zasada „jeden proces na granicę bezpieczeństwa” jest tu stosowana, nie zmieniana: zapis na koncie realnym to nowa
  reguła zapisu, więc dostaje własne procesy.
- `review.md` zostanie napisany po zadaniach — ta zmiana na niego zasługuje, bo pomyłka kosztuje prawdziwe pieniądze.

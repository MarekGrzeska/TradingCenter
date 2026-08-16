## Why

Wsparcia i opory to najczęstsza rzecz, którą operator nanosi na wykres, i jedyna, której
w tym terminalu nanieść się nie da. Agent umie je **policzyć** — `levels_near_price`
i wskaźniki grup `zones`/`structure` — ale nie umie ich **zostawić**: odpowiedź opisuje
poziom słowami, a po zamknięciu rozmowy nie zostaje po nim nic. Operator, który za tydzień
wraca do tego samego instrumentu, zaczyna od zera, a agent pytany „co tu wcześniej
ustaliliśmy" nie ma czego odczytać.

To także pierwsza rzecz w tym module, która ma być **trwała i wspólna**: polecenie wykresu
jest jednorazowe i należy do chwili, a poziom oporu należy do instrumentu i ma przeżyć
i rozmowę, i przeglądarkę.

## What Changes

- Nowa zdolność: **rysunki na wykresie** — obiekty przypisane do instrumentu, nie do slotu
  i nie do interwału, żyjące w bazie modułu `agent` obok poleceń wykresu.
- Trzy kształty: **poziom** (cena, opcjonalnie od wskazanego momentu), **strefa**
  (przedział dwóch cen, opcjonalnie od–do) oraz **linia trendu** (dwa punkty czas+cena).
  Każdy z etykietą i kolorem z palety terminala.
- Agent dostaje **dwa nowe narzędzia własne**: jedno rysujące i kasujące, drugie
  odczytujące to, co na instrumencie już jest. To pierwszy raz, kiedy moduł ma więcej niż
  jedno narzędzie własne — `agent-tools` mówi dziś wprost, że jest jedno.
- Moduł publikuje rysunki: odczyt po instrumencie oraz **poprawienie i usunięcie
  pojedynczego** — bo to, co narysował agent, operator MUST umieć cofnąć ręką.
- Terminal rysuje je nad serią, dokłada **linię trendu** jako nowy kształt rysowania
  (poziom i strefa mają już swoje prymitywy) i pokazuje **listę rysunków** aktywnego slotu,
  z której operator kasuje i poprawia.
- Terminal zaczyna **pisać** do modułu `agent`. Konsumuje go jak dotąd — nic od terminala
  nie zależy — ale kasowanie rysunku jest żądaniem, nie odczytem.

## Capabilities

### New Capabilities

- `agent-chart-drawings`: rysunki na wykresie — ich kształty, przypisanie do instrumentu,
  trwałość, numerowanie, narzędzia którymi agent je stawia i czyta, odmowy, oraz to, jak
  moduł je publikuje i pozwala operatorowi cofnąć.

### Modified Capabilities

- `agent-tools`: moduł ma więcej niż jedno narzędzie własne, a zakres jego zapisu obejmuje
  rysunki obok zawartości aktywnego slotu.
- `terminal-chart`: wykres rysuje obiekty pochodzące spoza katalogu wskaźników, umie
  narysować linię trendu i pokazuje listę rysunków, z której operator je kasuje.
- `terminal-agent-chat`: panel mówi także o tym, że agent narysował albo skasował obiekt.

## Impact

- `modules/agent`: nowa tabela `chart_drawings` i jej migracja, `agent/models.py`,
  `agent/store.py`, `agent/contract.py`, nowy router `agent/routers/drawings.py`, dwa nowe
  moduły narzędzi obok `agent/tools/chart.py`, rewizja promptu systemowego nazywająca je.
- `modules/terminal`: `src/agent/agentApi.ts` (odczyt, poprawka, usunięcie), nowy
  `src/chart/TrendlinePrimitive.ts`, `src/chart/Chart.tsx` (synchronizacja rysunków),
  nowa lista rysunków w UI slotu, `src/agent/chartControl.ts` albo jej sąsiad — odświeżenie
  po turze.
- Bez zmian: `market-data`, `market-mcp`, `capital-gateway`, `infra/`. Kontrakt
  `market_data/contract.py` nietknięty, więc `pnpm contract:generate` nie jest potrzebny.
- Zależność: `agent-chart-navigation` nie jest wymagana, ale obie zmiany dotykają
  `agent/tools/`, `agent/contract.py` i `Chart.tsx` — warto je robić po kolei, nie równolegle.

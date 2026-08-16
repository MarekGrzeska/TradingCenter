## Why

Agent umie dziś ustawić **co** wykres rysuje — symbol, interwał, wskaźniki — ale nie umie
ustawić **na co operator patrzy**. Prośba „pokaż mi to wybicie z trzeciego stycznia"
kończy się zdaniem opisującym datę, którą operator musi potem sam odnaleźć przewijaniem;
prośba „przybliż ostatnie sto świec" kończy się tak samo. Narzędzie, które ustawia wykres,
a nie umie go przesunąć, zatrzymuje się pół kroku przed tym, po co powstało.

Drugie, ten sam kadr: dzisiejsza zmiana interwału gubi to, na co operator patrzył.
`Chart.tsx` czyści serię przy zmianie rozdzielczości i pierwszy `redraw` nowej serii robi
`fitContent()` — więc przełączenie MINUTE_5 → HOUR nad wybiciem sprzed trzech dni pokazuje
całą świeżo wczytaną historię, a nie to wybicie w nowym interwale. Operator, i agent
proszony o zmianę interwału, tracą miejsce za każdym razem.

## What Changes

- Polecenie wykresu (`set_chart`) dostaje **kadr**: deklaratywne pole mówiące, jaki
  fragment osi czasu ma być widoczny. Trzy sposoby wskazania miejsca — zakres „od–do",
  punkt w czasie z liczbą świec wokół niego, oraz ostatnie N świec. Pole pominięte znaczy
  „zostaw kadr jak jest", tak samo jak reszta pól tego polecenia.
- Narzędzie **odmawia** kadru, którego terminal nie mógłby pokazać, nazywając, co
  poprawić: przedział odwrócony albo pusty, liczba świec poza granicami, kadr w całości
  późniejszy niż to, co archiwum ma.
- Terminal **stosuje kadr** do aktywnego slotu, dociągając starszą historię, jeśli kadr
  sięga przed najstarszą narysowaną świecę — zamiast pokazywać pusty fragment osi.
- **Zmiana interwału zachowuje kadr**: wykres zostaje nad tym samym odcinkiem czasu,
  przyciętym do rozsądnej liczby świec nowego interwału, a wykres stojący przy prawej
  krawędzi przy niej zostaje. Dotyczy zmiany zrobionej ręką operatora tak samo jak tej z
  polecenia agenta.
- **Migawka tury niesie kadr**: model, zanim zacznie przesuwać, wie, na jaki odcinek czasu
  operator właśnie patrzy.

## Capabilities

### New Capabilities

Brak — to jest rozszerzenie narzędzia i wykresu, które już istnieją.

### Modified Capabilities

- `agent-chart-control`: polecenie niesie kadr obok symbolu, interwału i wskaźników;
  odmowa obejmuje kadr, którego terminal nie mógłby pokazać.
- `agent-chat`: migawka tury niesie widoczny odcinek czasu, nie tylko symbol, interwał i
  wskaźniki.
- `terminal-chart`: wykres przyjmuje kadr z zewnątrz i dociąga pod niego historię; zmiana
  rozdzielczości zachowuje widziany odcinek czasu zamiast dopasowywać widok do całej serii.

## Impact

- `modules/agent`: `agent/tools/chart.py` (schemat i sprawdzenie kadru), `agent/models.py`
  (`ChartCommand`, `ChartSnapshot`), `agent/contract.py` (`ChartCommandOut`, migawka na
  wejściu tury), `agent/store.py`, nowa migracja dokładająca kolumnę kadru do
  `chart_commands`, prompt systemowy nazywający nowe pole.
- `modules/terminal`: `src/agent/chartControl.ts` (stosowanie kadru, `activeChartSnapshot`),
  `src/agent/agentApi.ts` (ręcznie pisane DTO), `src/grid/gridStore.ts` i `src/grid/model.ts`
  (kadr żądany dla slotu), `src/chart/Chart.tsx` (`redraw`, zmiana rozdzielczości,
  współpraca z `useOlderBars`).
- Bez zmian: `market-data`, `market-mcp`, `capital-gateway`, `infra/`. Kontrakt
  `market_data/contract.py` nietknięty, więc `pnpm contract:generate` nie jest potrzebny.

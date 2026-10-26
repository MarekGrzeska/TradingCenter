## Why

Metryki backtestu nie dowodzą reguł, które strategia miała spełniać. Średnia czasu trzymania pozycji nie mówi, że każda
pozycja zamknęła się przed końcem sesji; do tego potrzebna jest lista transakcji (tak wyszło przy przebiegu nr 2 z
25.10.2026, gdzie jedna transakcja trwała 169 dni, a podsumowanie pokazało tylko dziwną średnią). Lista już jest w bazie
i w zakładce, ale operator może ją oglądać tylko po 200 wierszy, bez pliku do arkusza, a agent nie może jej przeczytać
wcale: `strategies-tools` zabrania oddawania jej modelowi.

## What Changes

- Agent czyta transakcje uruchomienia nowym narzędziem `read_backtest_trades(run_id, offset, limit)`, do 100 na stronę,
  z czasami w UTC, cenami, wielkością, wynikiem, największą stratą otwartą, kosztami, przyczyną wyjścia i oznaczeniem
  rozstrzygnięcia pesymistycznego. `read_backtest` zostaje lekki i nadal nie oddaje transakcji.
- Operator pobiera wszystkie transakcje uruchomienia jako plik CSV z raportu. Plik ma czasy w UTC i w Warszawie, ceny,
  wielkość, wynik i koszty, i działa dla tysięcy transakcji, nie tylko dla strony tabeli.
- Nowa trasa REST `GET /runs/{run_id}/trades.csv`.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-tools`: narzędzie `read_backtest_trades`; wyjątek od zakazu oddawania modelowi listy transakcji.
- `strategies-api`: trasa `GET /runs/{run_id}/trades.csv`.
- `terminal-strategies`: pobranie transakcji uruchomienia jako CSV z raportu.

`strategies-reports` bez zmian: lista transakcji i jej pola już tam są; zmienia się to, kto i jak ją czyta.

## Impact

- `modules/workbench/strategies`: `routers/runs.py` (trasa), nowy `trades_csv.py` (kolumny i formatowanie), `tools/running.py`,
  `caller_access.py` (nowa ścieżka na liście tras), `contract.py` (model transakcji dla narzędzia), README pakietu.
- Powierzchnia narzędzi rozmowy rośnie o jedno narzędzie; sufit znaków w `tests/strategies/test_tools.py` może wymagać
  podniesienia o to, co opis naprawdę zajmie.
- `modules/terminal`: `ReportPanel.tsx`, `strategiesApi.ts`. Trasa CSV nie ma modelu odpowiedzi, więc wygenerowany
  kontrakt zyskuje tylko wpis ścieżki.
- Bez migracji i bez zmiany silnika.
- Delta `strategies-tools` opiera się na wersji wymagania „Powierzchnia narzędzi pakietu strategii” z
  `delete-old-backtests` (z `delete_backtests`), więc tamta zmiana MUST zostać zarchiwizowana pierwsza.

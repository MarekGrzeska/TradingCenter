## Why

Zakładka Backtests (25.10.2026) pokazuje uruchomienia różnych strategii na jednej liście, ale zestawić ich metryki obok
siebie umie tylko agent, przez `compare_runs`. Operator, żeby porównać dwa warianty parametrów, musi otwierać raporty po
kolei albo prosić o to rozmowę. Reguła porównywalności (ten sam zakres, koszty i silnik) już istnieje i jest sprawdzona;
brakuje jej drogi na ekran.

## What Changes

- Nowa trasa REST pakietu strategii: `GET /runs/compare?run_id=…&run_id=…` dla dwóch do pięciu zakończonych uruchomień.
  Odpowiada zestawieniem metryk albo odmową 422, która nazywa każdą różnicę, tę samą co narzędzie agenta.
- Sprawdzenie liczby uruchomień (2–5, bez powtórzeń) przechodzi z narzędzia do `compare.py`, żeby trasa i narzędzie
  stosowały jedną regułę z jednego miejsca.
- Zakładka Backtests: pole zaznaczenia przy każdym zakończonym uruchomieniu, przycisk „Porównaj” czynny dla 2–5
  zaznaczonych i tabela porównania: kolumna na uruchomienie (strategia, rewizja, parametry), wiersz na metrykę. Odmowa
  pokazuje różnice słowami. Tabela nie wskazuje lepszego uruchomienia, tak jak narzędzie.
- Wygenerowany kontrakt terminala dostaje model porównania.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-api`: trasa porównania uruchomień.
- `terminal-strategies`: porównanie zaznaczonych uruchomień w zakładce Backtests.

`strategies-tools` bez zmian: wymaganie „Porównanie tylko porównywalnych uruchomień” zostaje, a trasa odwołuje się do tej
samej reguły.

## Impact

- `modules/workbench/strategies`: `compare.py` (sprawdzenie liczby), `routers/runs.py` (trasa przed `/runs/{run_id}`),
  `contract.py` (`ComparisonOut`), `tools/running.py` (korzysta z przeniesionego sprawdzenia).
- `modules/terminal`: `strategiesApi.ts` (`compare`), `RunsPanel` (zaznaczenie), nowy `ComparePanel`, `BacktestsView`,
  wygenerowany kontrakt strategii (`contract-sync`).
- Bez migracji i bez nowych danych: porównanie czyta raporty, które już są zapisane. Koszt bazy: do pięciu odczytów po
  kluczu głównym, tylko na kliknięcie.
- `review.md` pominięty: zmiana mała, bez nowej granicy bezpieczeństwa; dostęp jak reszta tras pakietu (tylko `admin`).

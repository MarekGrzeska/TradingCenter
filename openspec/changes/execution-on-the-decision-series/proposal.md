## Why

Backtest nr 2 (US100 M5, 1.01–25.10.2026) dał −12,83% z jednej transakcji trzymanej 169 dni. Silnik wypełnia każde
zlecenie na serii `MINUTE`, a archiwum ma minuty US100 dopiero od 11.08.2026, poza czterema minutami 22.02. Zlecenie
rynkowe z 2 stycznia czekało więc do 22 lutego, a wyjście do 11 sierpnia. Przez ten czas pozycja blokowała każde
wejście, a raport nie powiedział o tym ani słowa. Tymczasem świece M5 za ten okres są pełne (44 533). Strategia, która
wchodzi zleceniem rynkowym i wychodzi tylko według czasu, nie potrzebuje minut: otwarcie następnej świecy decyzji jest
otwarciem pierwszej minuty po decyzji.

## What Changes

- Silnik wybiera serię wykonania z dokumentu. Strategia bez poziomów, które trzeba sprawdzać w środku świecy (bez
  `stop`, `target`, `trail` i bez zleceń wejścia `limit` i `stop`), wykonuje się na serii decyzji. Nie czyta wtedy
  `MINUTE`, więc test może sięgać tak daleko jak historia interwału decyzji.
- Strategia z takimi poziomami zostaje na `MINUTE`. Gdy pod świecą decyzji w zakresie nie ma żadnej minuty, uruchomienie
  kończy się niepowodzeniem, zanim cokolwiek policzy. Komunikat podaje liczbę takich świec, pierwsze luki i pierwszą
  minutę w archiwum. Zlecenie nie może już czekać na dane przez miesiące.
- Limit długości zakresu jest liczony w świecach serii wykonania, nie zawsze w minutach. Odczyt rewizji podaje serię
  wykonania, a formularz uruchomienia w terminalu liczy świece tej serii.
- Raport i `read_backtest` podają serię wykonania.
- Wersja silnika rośnie z 3 do 4, bo zmienia się wynik każdego uruchomienia, w którym brakowało minut.

`compare_runs` się nie zmienia. Strategia ze stopem i strategia bez stopu, porównane na tym samym zakresie i kosztach,
mierzą to samo, bo zlecenie rynkowe wypełnia się po tej samej cenie na obu seriach. Seria wykonania jest widoczna w
raporcie każdej z nich.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-backtest`: seria wykonania zależy od dokumentu; brak minut pod strategią z poziomami to niepowodzenie z
  nazwaną przyczyną; limit zakresu liczony w świecach serii wykonania.
- `strategies-reports`: raport zapisuje serię wykonania.
- `strategies-api`: odczyt rewizji podaje serię wykonania; sufit zakresu nazwany w świecach serii wykonania.
- `terminal-strategies`: formularz uruchomienia liczy świece serii wykonania, nie minuty.

## Impact

- `modules/workbench/strategies`: `engine.py` (pętla wykonania), `reading.py` i `requirements.py` (co się czyta),
  `runs.py` (limit przed zakolejkowaniem), `worker.py` i `reports.py` (krzywa kapitału i kup-i-trzymaj z serii
  wykonania), `queue.py` (sprawdzenie minut), `contract.py`, złoty plik silnika.
- Kontrakt REST: `RevisionOut.execution` (nowe pole), `HealthOut.max_minute_bars` → `max_execution_bars` (**BREAKING**
  dla jedynego konsumenta, terminala, wdrażanego tym samym deployem). Seria wykonania raportu trafia do istniejącego pola
  `provenance`.
- `modules/terminal`: `RunForm.tsx`, `strategiesApi.ts`, wygenerowany kontrakt strategii.
- Ustawienie `STRATEGIES_MAX_MINUTE_BARS` → `STRATEGIES_MAX_EXECUTION_BARS`; stara nazwa trafia do `RETIRED_SETTINGS`.
- Zapisane uruchomienia zostają takie, jakie były, z wersją silnika 3.
- Delta `strategies-reports` opiera się na wersji wymagania z `a-trade-held-through-the-session`, więc tamta zmiana MUST
  zostać zarchiwizowana pierwsza.

## Why

Uruchomienia strategii tylko przybywają. Lista w zakładce Backtests rośnie o każdy wariant, o każdy przebieg zrobiony na
błędnych danych (jak przebieg nr 2 z 25.10.2026, policzony nad dziurą w minutach) i o każdy anulowany czy nieudany.
Operator nie ma jak ich usunąć, a agent tym bardziej. Usuwanie nie może jednak wymazać śladu prób: licznik prób to
liczba, według której ocenia się nadmierne dopasowanie, i zniknięcie z niego nieudanych wariantów zrobiłoby z czyszczenia
listy sposób na ukrycie, ile razy strategię testowano.

## What Changes

- Operator usuwa uruchomienia w zakładce Backtests: zaznacza je i wybiera „Usuń”, po potwierdzeniu. Dotyczy to uruchomień
  zakończonych, nieudanych i anulowanych. Uruchomienie czekające albo liczone trzeba najpierw anulować.
- Agent usuwa uruchomienia narzędziem rozmowy `delete_backtests` (do 20 identyfikatorów naraz), wyłącznie na wyraźną
  prośbę operatora, co mówi opis narzędzia.
- Usunięcie kasuje raport, żądanie, pochodzenie wyniku i transakcje. Licznik prób strategii **nie maleje**: liczba
  usuniętych zakończonych uruchomień zostaje zapisana przy strategii i dodaje się do licznika.
- Operacja jest wszystko albo nic: jeśli którekolwiek z podanych uruchomień nie istnieje albo jeszcze się liczy,
  nic nie jest usuwane, a odmowa nazywa każde takie uruchomienie.
- Pakiet strategii dostaje trasę `DELETE /runs` (powtórzone `run_id`, do 20) i kolumnę z liczbą usuniętych prób
  (migracja `0006`, stosowana przez sam pakiet przy starcie).
- `read_backtest`, `compare_runs` i trasy odczytu mówią o usuniętym uruchomieniu to, co o nieistniejącym, i dodają, że
  mogło zostać usunięte.

Dostęp bez zmian: cały pakiet strategii jest już zamknięty przed rolą `viewer`, więc usuwać może tylko operator z rolą
`admin`.

## Capabilities

### New Capabilities
Brak.

### Modified Capabilities
- `strategies-backtest`: usunięcie uruchomienia i licznik prób, który go przeżywa.
- `strategies-api`: trasa `DELETE /runs`.
- `strategies-tools`: narzędzie `delete_backtests` na powierzchni pakietu.
- `terminal-strategies`: zaznaczanie i usuwanie uruchomień w zakładce Backtests.

## Impact

- `modules/workbench/strategies`: `runs.py` (usunięcie), `store.py` (licznik prób), `routers/runs.py`,
  `tools/running.py`, `contract.py`, migracja `migrations/strategies/versions/0006_deleted_trials.py`, README pakietu.
- Powierzchnia narzędzi rozmowy rośnie o jedno narzędzie; sufit znaków w `tests/strategies/test_tools.py` ma zapas
  (10 367 z 11 500) i zostaje albo rośnie o to, co opis naprawdę zajmie.
- `modules/terminal`: `RunsPanel.tsx`, `BacktestsView.tsx`, `strategiesApi.ts`, wygenerowany kontrakt strategii.
- Delta `strategies-tools` opiera się na wersji wymagania „Powierzchnia narzędzi pakietu strategii” z
  `agent-drafts-in-the-editor` (z `draft_strategy`), więc tamta zmiana MUST zostać zarchiwizowana pierwsza.
- Migracja dodaje kolumnę z wartością domyślną 0 i nie zmienia istniejących wierszy; nie jest krokiem operatora.

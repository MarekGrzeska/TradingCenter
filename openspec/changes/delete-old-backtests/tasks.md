## 0. Kolejność

- [x] 0.1 Zarchiwizować `agent-drafts-in-the-editor` (jest wdrożona), bo ta zmiana modyfikuje jej wersję wymagania
  „Powierzchnia narzędzi pakietu strategii”.

## 1. Baza i usunięcie

- [x] 1.1 Migracja `0006`: `strategies.deleted_trials` z domyślnym 0 i `downgrade`; test migracji.
- [x] 1.2 `store._SUMMARY`: licznik prób to `count(done)` plus `deleted_trials`.
- [x] 1.3 `runs.delete`: blokada wierszy, odmowa dla nieistniejących i w toku (D2), usunięcie transakcji i uruchomień,
  dopisanie usuniętych `done` do `deleted_trials` per strategia; testy `-m db` na każdy scenariusz
  `strategies-backtest`, w tym wyścig z końcem uruchomienia.

## 2. REST i narzędzie

- [x] 2.1 `DELETE /runs` (D3) z odpowiedzią w `contract.py`, kodami 404, 409, 422; test odmów i test usunięcia.
- [x] 2.2 `delete_backtests` w `tools/running.py` z opisem z D4, odmowy takie jak trasy; `read_backtest` i `compare_runs`
  mówią o możliwym usunięciu (D5); aktualizacja `EXPECTED` i sufitu znaków w `tests/strategies/test_tools.py`.
- [x] 2.3 Skill `contract-sync`: wygenerowany kontrakt terminala.

## 3. Ekran

- [x] 3.1 `strategiesApi.ts`: `deleteRuns(ids)`; odmowa pakietu jako `Refused`.
- [x] 3.2 `RunsPanel.tsx` i `BacktestsView.tsx`: druga kolumna zaznaczeń, „Usuń” z `ConfirmDialog` (D6), odświeżenie listy,
  zamknięcie otwartego raportu usuniętego uruchomienia; testy trzech scenariuszy z `terminal-strategies`.

## 4. Dokumentacja i zamknięcie

- [x] 4.1 `strategies/README.md`: usuwanie, licznik prób, który przeżywa.
- [x] 4.2 `review.md` po angielsku według szablonu.

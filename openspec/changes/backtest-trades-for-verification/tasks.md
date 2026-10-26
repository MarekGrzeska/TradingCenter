## 0. Kolejność

- [x] 0.1 Zarchiwizować `delete-old-backtests` (po wdrożeniu), bo ta zmiana modyfikuje jego wersję wymagania „Powierzchnia
  narzędzi pakietu strategii”.

## 1. Trasa CSV

- [x] 1.1 `trades_csv.py`: kolumny, czasy w UTC i w `Europe/Warsaw`, puste pola, BOM (D4); testy jednostkowe formatu, w tym
  lata z przesunięciem letnim i zimowym oraz transakcja bez stopu.
- [x] 1.2 `GET /runs/{run_id}/trades.csv` jako strumień stron (D3) z 404 i samym nagłówkiem dla uruchomienia bez
  transakcji; ścieżka w `caller_access.REST_PATHS`; testy `-m db` dwóch scenariuszy z `strategies-api` i 404.
- [x] 1.3 Skill `contract-sync`: wygenerowany kontrakt terminala.

## 2. Narzędzie agenta

- [x] 2.1 `read_backtest_trades` w `tools/running.py` (D1, D2): strona, łączna liczba, odmowy; opis z UTC, stroną i brakiem
  próby; aktualizacja `EXPECTED` i sufitu znaków w `tests/strategies/test_tools.py`.
- [x] 2.2 Testy: dwie strony po 100 z 154 transakcji, limit ponad sufit, transakcja bez stopu, `read_backtest` bez transakcji.

## 3. Ekran

- [x] 3.1 `strategiesApi.ts`: `downloadTrades(runId)` przez klienta z tożsamością (D5), nazwa pliku składana w terminalu.
- [x] 3.2 `ReportPanel.tsx`: „Pobierz transakcje (CSV)”, błąd słowami, strona tabeli nietknięta; testy obu scenariuszy z
  `terminal-strategies`.

## 4. Dokumentacja i zamknięcie

- [x] 4.1 `strategies/README.md`: dwa sposoby czytania transakcji i format pliku.
- [x] 4.2 `review.md` po angielsku według szablonu.

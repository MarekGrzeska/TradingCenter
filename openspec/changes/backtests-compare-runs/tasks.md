## 1. Pakiet strategii

- [x] 1.1 `compare.py`: sprawdzenie 2–5 różnych identyfikatorów jako funkcja; `compare_runs` z niej korzysta
- [x] 1.2 `contract.py`: `ComparedRunOut` (strategia, rewizja, parametry, pole na każdą metrykę z `METRICS`) i `ComparisonOut`
- [x] 1.3 `routers/runs.py`: `GET /runs/compare` przed `/runs/{run_id}` — 200, 404 z numerem, 422 z problemem na różnicę
- [x] 1.4 Testy: liczba i powtórzenia w `compare.py` (unit); jedna trasa 200 i jedna 422 przez HTTP (`db`)

## 2. Kontrakt

- [x] 2.1 `contract-sync`: wygenerowany kontrakt strategii terminala z `ComparisonOut`

## 3. Terminal

- [x] 3.1 `strategiesApi.ts`: `compare(runIds)` z mapowaniem przewodu na domenę i odmową 422 jako problemy
- [x] 3.2 `RunsPanel`: pole zaznaczenia przy zakończonych uruchomieniach; `BacktestsView` trzyma zaznaczone identyfikatory
- [x] 3.3 `ComparePanel`: tabela kolumna-na-uruchomienie, wiersz-na-metrykę, albo lista różnic z odmowy
- [x] 3.4 Testy widoku: porównanie pokazuje tabelę, odmowa pokazuje różnice, uruchomienia niezakończonego nie da się zaznaczyć

## 4. Domknięcie

- [x] 4.1 `uv run pytest` · `ruff` · `pyright` w workbenchu; `pnpm test` · `lint` · `typecheck` · `contract:check` w terminalu
- [x] 4.2 README pakietu: trasa porównania; usunąć „Porównanie w zakładce Backtests” z listy braków w `docs/strategie-stan-wdrozenia.html`

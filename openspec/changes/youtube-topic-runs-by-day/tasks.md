## 1. Backend

- [x] 1.1 `store.list_runs`: zakres `since`/`until` łączony z tematem (jedno zapytanie składane z warunków, bez `OR` na parametrze); test store
- [x] 1.2 `GET /topic-runs`: `since`/`until` (bez strefy = UTC, początek włączony, koniec wyłączony), odmowa zakresu odwróconego; jeden publiczny pomocnik strefy w `views.py`; testy REST
- [x] 1.3 README `youtube_data`

## 2. Terminal

- [x] 2.1 Skill `contract-sync`: `contract.youtube.generated.ts`
- [x] 2.2 `youtubeApi.topicRuns` z zakresem; `RunsPanel`: pola Od/Do w czasie lokalnym (oba końce włącznie), czyszczenie, komunikat pustego zakresu
- [x] 2.3 Testy widoku i klienta

## 3. Zamknięcie

- [x] 3.1 `openspec validate youtube-topic-runs-by-day --strict`, `pytest`, `ruff`, `pyright`, `vitest`, `eslint`, `tsc`, `contract:check`, EXPLAIN zakresu
- [x] 3.2 `review.md`

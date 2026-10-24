## Why

Przebieg wyszukiwania tematu zostawia po sobie dziś tylko nadpisywane `topics.last_run_at` i kandydatów. Przebieg, który niczego
nie znalazł, nie odróżnia się od takiego, który się nie odbył; błąd źródła i pominięcie z powodu pustego dnia nie zostawiają
nic poza linijką w logu, a operator, który pyta „dlaczego ten temat milczy”, nie ma gdzie zajrzeć.

## What Changes

- Każda próba wyszukiwania tematu zapisuje **wpis przebiegu**: temat, moment, wynik (`found` — są nowi kandydaci,
  `nothing_new` — źródło odpowiedziało, nic nowego, `failed` — źródło zawiodło, `skipped` — dzień źródła nie starcza) i
  raport: ile wyników zwróciło źródło, ile było już znanych lub z kanałów rozstrzygniętych, ile poza granicami długości,
  ile nowych kandydatów i jak przesianych, a dla `failed`/`skipped` — przyczyna.
- Gdy przesiew nie mógł się odbyć (brak modelu, wyczerpany dzień tokenów, odpowiedź poza schematem, błąd modelu), wpis mówi
  dlaczego kandydaci są „nieprzesiani”.
- Pominięcie z powodu dnia źródła jest zapisywane **raz na temat na dobę UTC**, a nie co przebieg pętli; porażka — za każdym razem.
  Porażka nadal nie przesuwa terminu następnego wyszukiwania (zachowanie bez zmian).
- Wpisy starsze niż 30 dni są usuwane przy zapisie kolejnego.
- REST: `GET /topic-runs` (filtr po temacie, od najnowszego); `GET /topics` niesie wynik ostatniego przebiegu każdego tematu.
- Terminal: w zakładce Kandydaci widok **Historia** (obok Otwartych, Odrzuconych i Z decyzją) z filtrem po temacie; w zakładce
  Tematy linijka z wynikiem ostatniego przebiegu.

Poza zakresem: przebiegi odkrywania kanałów; koszt przebiegu w jednostkach i tokenach (zostaje w `usage` per doba);
narzędzie dla agenta; powiadomienia o porażce przebiegu.

Pominięto w tej zmianie: nic — wszystkie artefakty powstają. Zdolności `youtube-data-*` zmieniane przez niezarchiwizowane
zmiany nie są jeszcze w `openspec/specs/`, więc delta to jedna nowa zdolność.

## Capabilities

### New Capabilities

- `youtube-data-topic-runs`: historia przebiegów wyszukiwania tematów z raportem, jej retencja i odczyt (REST, terminal).

### Modified Capabilities

Brak w `openspec/specs/`.

## Impact

- `modules/workbench`: migracja `0007` w łańcuchu `youtube` (tabela `topic_runs`), `youtube_data/store.py`, `ingest.py`,
  `models.py`, `contract.py`, `routers/watch.py` albo nowy `routers/runs.py`, `app.py`, README.
- `modules/terminal`: `contract.youtube.generated.ts` (skill `contract-sync`), `youtube/CandidatesPanel.tsx`,
  `WatchPanels.tsx`, `youtubeApi.ts`, `present.ts`.
- Produkcja: migracja wykonuje się sama przy starcie; bez nowych sekretów. Koszt bazy: jeden zapis na przebieg (klasa C1).

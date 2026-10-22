## 0. Przed kodem

- [ ] 0.1 Odczytać reguły alertów na produkcji (jeśli YouTube jest tam włączony). Każdą regułę filtrującą `youtube.film.read` po `topic` zapisać i pokazać operatorowi.

## 1. Baza

- [x] 1.1 Migracja `0004` w łańcuchu `youtube`:
  - `candidates` i `ignored_channels` z indeksami z design.md (pkt 1);
  - zdjęcie `topics.prompt_id`;
  - `downgrade` przywraca kolumnę z promptem zasianym.
- [x] 1.2 `db-cost-check` dla listy kandydatów w obu porządkach i dla wykluczeń przed przesiewem.
- [x] 1.3 `models.py` i `store.py`:
  - kandydaci: zapis z deduplikacją po `video_id`; lista z porządkiem, zawężeniem po temacie, werdykcie i decyzji;
  - decyzja z oznaczeniem pozostałych kandydatów kanału;
  - ignorowane kanały: lista, dopisanie, zdjęcie;
  - temat bez promptu.

## 2. Przesiew i pętla

- [x] 2.1 `VideoRef` z opisem z `snippet.description` w `data_api.video_details`, przyciętym do 1 000 znaków.
- [x] 2.2 `screening.py`:
  - protokół `Screener`, ramka „dane obce”, ścisły schemat `{items: [{video_id, verdict, reason_pl}]}`;
  - `OpenAIScreener` na kliencie i modelu analizatora;
  - tokeny w `Meter` i w `DAILY_TOKEN_LIMIT`.
- [x] 2.3 `providers/build.py` składa screener (sim / openai / brak). `GET /state` mówi, dlaczego przesiew nie działa.
- [x] 2.4 `ingest.py`, gałąź tematów:
  - wyniki przechodzą przez progi długości i wykluczenia (archiwum, obserwowane, ignorowane, już kandydaci);
  - przesiew jednym wywołaniem;
  - zapis do `candidates`, nigdy `upsert_films`;
  - przy braku modelu, limicie albo błędzie odpowiedzi kandydaci są `unscreened`.
- [x] 2.5 `sim/`: `SimScreener` i werdykty w scenariuszu, także opis-intruz próbujący wymusić „proposed”.
- [x] 2.6 Testy przesiewu: szum odrzucony; element bez werdyktu daje `unscreened`; brak klucza; dzień bez tokenów; wykluczenia nie płacą tokenów.

## 3. Powierzchnie

- [x] 3.1 `contract.py` i nowy `routers/candidates.py`:
  - `GET /candidates` (`sort=found|published`, `topic`, `verdict`, `decided`);
  - `POST /candidates/{id}/follow-channel`, `/analyse` (oba z opcjonalnym `prompt_id`), `/dismiss`, `/ignore-channel`;
  - `GET|POST /ignored-channels`, `DELETE /ignored-channels/{channel_id}`.
- [x] 3.2 `watchlist.py`:
  - „obserwuj kanał” i „analizuj film” idą przez istniejące `follow_channel` i `analyse_film`, a odmowa sufitu zostawia kandydata bez decyzji;
  - `add_topic` bez promptu.
- [x] 3.3 `TopicOut`, `TopicIn` i `TopicPatch` bez `prompt_id`; temat z promptem jest odmawiany z powodem. `PromptOut.topics` znika.
- [x] 3.4 Narzędzia: `add_topic` bez `prompt`. Test listy narzędzi rozszerzony o warunek, że żadne nie decyduje o kandydacie.
- [x] 3.5 Testy HTTP kandydatów: jeden happy path na decyzję, odmowa sufitu, odmowa dostępu.
- [x] 3.6 README pakietu: tabela zapisów, droga tematu, trasy i narzędzia.

## 4. Terminal

- [x] 4.1 `contract-sync`: regeneracja `contract.youtube.generated.ts`.
- [x] 4.2 `youtubeApi.ts`: kandydaci, decyzje, ignorowane kanały. Temat bez promptu.
- [x] 4.3 `CandidatesPanel` i sekcja Kandydaci w `YoutubeView`:
  - porządek, temat i przełącznik „odrzuceni przez model”;
  - cztery akcje (z wyborem promptu przy obserwacji i analizie);
  - odnośnik do YouTube w nowej karcie;
  - lista ignorowanych z cofnięciem.
  Trzy testy widoku.
- [x] 4.4 `TopicsPanel` bez wyboru promptu. `PromptsPanel` bez przypisań do tematów.

## 5. Wydanie

- [x] 5.1 Workbench: `uv run pytest` (z `-m db`), `ruff check .`, `pyright`. Terminal: `pnpm test`, `lint`, `typecheck`, `contract:check`.
- [ ] 5.2 PR, merge, `deploy-watch`. Po wdrożeniu przekazać operatorowi reguły z 0.1.

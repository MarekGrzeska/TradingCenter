## 1. Baza i model

- [x] 1.1 Migracja `0006` w łańcuchu `youtube`: `channels.filter` (NULL, 1–1000 znaków), `filtered_out` w `videos_state_is_known`, CHECK powodu dla `filtered_out`; `downgrade`
- [x] 1.2 `models.py`: stała `FILTERED_OUT` w `STATES`, `Channel.filter`
- [x] 1.3 `store.py`: odczyt i zapis `filter` w `add_channel`/`update_channel` (z usunięciem), zapis filmu odrzuconego z powodem, `list_videos` pomija `filtered_out` bez wskazanego stanu
- [x] 1.4 Test migracji (`-m db`) i testy store dla nowego stanu

## 2. Ocena w pętli

- [x] 2.1 `screening.py`: ramka kryteriów kanału obok tematowej, wspólny schemat i `verdicts_from`; test wiadomości (kryteria osobno, metadane jako dane obce)
- [x] 2.2 `ingest._discover`: dla kanału z filtrem — nieznane filmy (`already_known`) do jednego wywołania screenera; przepuszczone zapisane jak dziś, odrzucone jako `filtered_out`, nieocenione niezapisane; tokeny do licznika
- [x] 2.3 `GET /state`: przyczyna, gdy filmy kanałów z filtrem czekają (brak modelu, wyczerpany dzień)
- [x] 2.4 Testy pętli: przepuszczony, odrzucony, nieoceniony czeka i jest oceniony po odnowieniu, brak werdyktu dla jednego filmu, odrzucony nieoceniany drugi raz, kanał bez filtra bez wywołania modelu
- [x] 2.5 Symulacja: scenariusz `sim` z kanałem, którego filmy filtr dzieli

## 3. Ręczne przetworzenie i powierzchnie

- [x] 3.1 `watchlist.follow_channel` przyjmuje filtr z walidacją; `analyse_film` przetwarza `filtered_out` (przejście do `discovered`, czyszczenie powodu, `manual` w `origins`)
- [x] 3.2 `contract.py`: `filter` w `ChannelOut`/`ChannelIn`/`ChannelPatch` (jawne usunięcie), `filtered_out` i powód w filmie; `routers/watch.py`, `routers/videos.py`
- [x] 3.3 Narzędzie `follow_channel`: opcjonalny `filter`, opis mówi, że zmienia go tylko operator
- [x] 3.4 Testy REST i narzędzia: po jednym na zapis filtra, odmowę (za długi) i „Analizuj mimo to”
- [x] 3.5 README `youtube_data`: filtr w drodze filmu, stan `filtered_out`, czekanie przy braku oceny

## 4. Terminal

- [x] 4.1 Skill `contract-sync`: `contract.youtube.generated.ts`
- [x] 4.2 `WatchPanels.tsx`: pole filtra przy dodawaniu i edycji kanału, oznaczenie kanału z filtrem
- [x] 4.3 Lista filmów: stan „pominięty przez filtr” w wyborze stanu, powód na karcie, akcja „Analizuj mimo to”; `present.ts`
- [x] 4.4 Testy widoku: zapis filtra, błąd zapisu, „Analizuj mimo to”

## 5. Zamknięcie

- [x] 5.1 `openspec validate youtube-channel-filter --strict`, `uv run pytest -m db`, `ruff`, `pyright`, `pnpm test`/`lint`/`typecheck`/`contract:check`
- [x] 5.2 `review.md`

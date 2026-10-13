## Why

Film wskazany ręcznie — z terminala albo narzędziem `analyse_video` — dziś trafia do kolejki i czeka na
najbliższy przebieg pętli, czyli do pół godziny. Operator, który wkleił link, patrzy na „czeka na
transkrypcję” i nie wie, czy coś jest zepsute (zdarzyło się 13 października 2026, godzinę po włączeniu pakietu
na produkcji). Ktoś, kto wskazuje film wprost, chce jego oceny teraz, nie po kolejce kanałów i tematów.

## What Changes

- Film wskazany ręcznie jest **transkrybowany, odczytywany i, jeśli reguła każe, ogłaszany od razu**, w tle,
  poza kolejką: bez czekania na odstęp pętli i bez przepuszczania innych filmów z kolejki.
- Odpowiedź na wskazanie wraca natychmiast („przyjęty, przetwarzany teraz”); przetwarzanie trwa w tle,
  bo Gemini słucha filmu minutami.
- Te same zasady co w pętli: sufity dzienne, cena przed pytaniem, odpoczynek zablokowanego dostawcy, ponowienia
  i `gave_up`. Różnica jedna: wskazanie **pomija czas oczekiwania na ponowienie** (`next_attempt_at`), bo operator
  prosi wprost. Film, który już jest odczytany albo porzucony, nie jest przetwarzany drugi raz.
- Jedna pętla, jeden zamek: przetwarzanie „teraz” i przebieg pętli nie biegną równocześnie, więc nie wydadzą
  tego samego sufitu dwa razy.

Poza zakresem: zmiana komunikatu na ekranie dla filmów z kolejki (osobno), przetwarzanie od razu filmów
odkrytych przez kanał albo temat (zostają pętli).

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-ingest`: wyjątek od „odkrywanie i przetwarzanie należą do pętli” — film wskazany ręcznie
  przetwarza się od razu. Zdolność powstaje w `add-youtube-archive` (zmergowane, jeszcze niezarchiwizowane);
  **ta zmiana MUST zostać zarchiwizowana po niej**.

Pominięte: `design.md` (decyzje są w tym dokumencie) i `review.md` (mały zakres, testy na zamek i sufity).

## Impact

- `modules/workbench/youtube_data`: `ingest.py` (zamek, przetwarzanie jednego filmu), `store.py` (wybór filmu
  po identyfikatorze), `routers/videos.py` i `tools/watch.py` (uruchomienie w tle), README, opisy narzędzia.
- Produkcja: po wdrożeniu workbencha; bez zmian infrastruktury.

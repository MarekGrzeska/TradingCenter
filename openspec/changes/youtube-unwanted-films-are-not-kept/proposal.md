## Why

Pominięte filmy (shorty, wielogodzinne transmisje) zostawały w archiwum ze stanem „pominięty” i powodem.
Pierwszego dnia na produkcji było ich 11 z 16 — zaśmiecały listę w zakładce i każdą odpowiedź narzędzi, a
nikt ich nie czyta ani nie analizuje.

## What Changes

- Film, którego długość jest znana i wypada poza progami (dolny: 3 minuty, górny: 3 godziny), **nie jest
  zapisywany w archiwum w ogóle** — ani przy odkryciu przez kanał lub temat, ani przy wskazaniu ręcznym.
- Film, który okaże się za krótki lub za długi dopiero po zapisaniu (premiera dostaje długość późno), jest
  **usuwany w przebiegu pętli**. To samo dotyczy wierszy w stanie „pominięty” zostawionych przez starszą wersję.
- Ponownie listowany film spoza progów nie wraca do archiwum, więc pętla nie zapisuje go i nie kasuje co przebieg.
- Wskazanie ręczne filmu spoza progów jest **odrzucone z powodem** („krótszy niż 180 s”) zamiast po cichu
  zapisane i ukryte.
- Transmisja na żywo nadal czeka, aż się skończy.

Poza zakresem: stan „pominięty” zostaje w schemacie i kontrakcie (nikt go już nie ustawia), żeby nie ruszać
wygenerowanego kontraktu ani migracji; usunięcie go to osobne sprzątanie.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `youtube-data-ingest`: filmy, których nie warto czytać, nie są przechowywane. Zdolność powstaje w
  `add-youtube-archive` (zmergowane, jeszcze niezarchiwizowane); **ta zmiana MUST zostać zarchiwizowana po niej**.

Pominięte: `design.md` i `review.md` (mały zakres; testy na to, że film spoza progów nie wraca i że ręczne
wskazanie jest odrzucone z powodem).

## Impact

- `modules/workbench/youtube_data`: `store.py` (filtr przy zapisie, kasowanie zamiast pomijania), `ingest.py`,
  `watchlist.py`, README; `docs/youtube-jak-dziala.html`.
- Produkcja: po wdrożeniu pierwszy przebieg usuwa 11 istniejących pominiętych wierszy; bez zmian infrastruktury.

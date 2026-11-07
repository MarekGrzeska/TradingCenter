## Why

Operator chce śledzić wybrane kanały YouTube i tematy, a z filmów dostawać streszczenie,
sentyment per instrument i alert na Telegram — dziś system nie widzi YouTube wcale. Research
(`docs/youtube-archiwum-projekt.html`, `docs/supadata-koszty.html`) pokazał, że jedyną drogą
wymagającą pieniędzy i decyzji jest transkrypcja z produkcji (Azure jest blokowany przez YouTube).
Wszystko inne — pakiet, dane, pętla, narzędzia, ekran, alerty — da się zbudować i ćwiczyć lokalnie
za zero, jeśli dostawcy stoją za interfejsem, a ich zachowanie jest wiernie symulowane.

## What Changes

- Nowy, dziewiąty pakiet workbencha `youtube_data`, zamontowany pod `/youtube`, z własną bazą
  `youtube` i własnym łańcuchem migracji pod kluczem blokady `8110`.
- Lista obserwacji: kanały i tematy wyszukiwania, dopisywane przez operatora (REST, terminal) i przez
  agenta (narzędzia); zdjęcie z listy wyłącznie przez REST.
- Pętla: odkrycie filmu → transkrypcja → odczyt modelu → alert, ze stanem filmu w bazie,
  skończoną liczbą ponowień i limitami partii oraz budżetem jednostek każdego dostawcy.
- Trzy interfejsy dostawców z implementacjami darmowymi: źródło filmów (`rss`, `data_api` na
  darmowym kluczu, `sim`), transkrypcja (`direct` przez `youtube-transcript-api` z domowego IP,
  `sim`), odczyt (`openai` za kluczem, `sim`).
- **Symulator** odtwarzający zachowania prawdziwych dostawców ze scenariusza: filmy pojawiające się
  w czasie, napisy dostępne dopiero po godzinach, blokada IP, zadanie asynchroniczne, płatny brak
  napisów, wyczerpany limit jednostek, model odmawiający odpowiedzi, opóźnienia. Dane symulowane są
  oznaczone wszędzie, gdzie wychodzą, i nie ruszają w trybie produkcyjnym.
- REST z trasą stanu, 10 narzędzi dla rozmowy i zespołów, zakładka YouTube w terminalu,
  alerty przez `/telegram` w procesie.
- Brak `YOUTUBE_DATABASE_URL` jest działającą konfiguracją: pakiet się nie montuje. Dzięki temu
  zmiana może wchodzić do `main` małymi PR-ami, zanim produkcja dostanie bazę.

**Poza zakresem:** produkcyjny dostawca transkrypcji (Supadata, proxy, Gemini), Terraform i baza
produkcyjna, retencja 30 dni wymagana przez ToS danych z API (dopiero z produkcją), pocket,
weryfikacja prognoz względem `/market`. Każde z nich to osobna zmiana.

## Capabilities

### New Capabilities
- `youtube-data-watchlist`: kanały i tematy — kto je dopisuje, sufit, jedyne wyjście z listy.
- `youtube-data-ingest`: pętla, odkrywanie filmów, cykl życia filmu, ponowienia, co jest pomijane.
- `youtube-data-transcripts`: dostawca transkrypcji za interfejsem, rozróżnienie braku napisów od
  blokady, budżet jednostek i kredytów.
- `youtube-data-enrichment`: odczyt modelu — schemat, transkrypcja jako dane obce, stan bez klucza,
  dzienny limit tokenów.
- `youtube-data-simulation`: symulowani dostawcy sterowani scenariuszem, znakowanie danych, zakaz
  w trybie produkcyjnym.
- `youtube-data-alerts`: reguły alertu kanału i progu, znacznik po udanej wysyłce.
- `youtube-data-tools`: zestaw narzędzi — co czyta, co pisze, co kosztuje, jak podaje surowy tekst.
- `youtube-data-api`: kontrakt REST, trasa stanu, dostęp wołających, wiek przebiegu pętli.
- `terminal-youtube`: zakładka terminala — filmy, kanały, tematy, pasek stanu.

### Modified Capabilities
- `workbench-process`: dochodzi wymaganie, że pakiet YouTube jest obecny z konfiguracji albo
  nieobecny — nigdy „zamontowany, ale bez bazy".

## Impact

- `modules/workbench`: nowy pakiet `youtube_data/`, `alembic-youtube.ini`, montaż w
  `workbench/app.py`, wpis w `tests/test_layering.py`, podpięcie w `workbench/local_tools.py`,
  blok `YOUTUBE_*` w `.env.example`; zależność `youtube-transcript-api`.
- `scripts/dev.py`: baza `youtube` w `LOGICAL_DATABASES` i łańcuch migracji na liście.
- `modules/terminal`: `src/youtube/`, wygenerowany `contract.youtube.generated.ts`.
- Produkcja: bez zmian — ustawienie nie istnieje, pakiet się nie montuje.
- `review.md` zostanie napisany po zadaniach: zmiana wprowadza zapis przez narzędzia i nową
  zależność zewnętrzną, więc na niego zasługuje.

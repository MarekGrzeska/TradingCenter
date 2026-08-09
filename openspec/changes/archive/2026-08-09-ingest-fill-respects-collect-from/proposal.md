## Why

Dodanie pary z jawną, płytką datą OD dociąga historię, o którą operator nie prosił — cicho, bez
odmowy i bez śladu w niczym, co operator wtedy widzi. Dwa niezależne mechanizmy robią to na dwa
niezależne sposoby, a znalezione zostały jeden po drugim, bo pierwszy zasłaniał drugi.

**Pierwszy: cichy fill ignoruje `collect_from`.** Ujawniło to dodanie kolumny „Data since"
w `Instruments`: operator dodał US100 w interwałach od `5m` do `1W`, z datą OD 2026-01-01. Zlecenie
policzyło i pobrało dokładnie to, o co poproszono — sprawdzone w `collection_job_chunks`, każdy
kawałek zaczyna się od 2026-01-01. Ale obok zlecenia, w tym samym momencie, żywy ingest uruchomił
dla tej samej pary własne domykanie luki (`PairIngest._close_gap` → `fill_gap`), które dla pary bez
żadnej świecy sięga po stałą, skonfigurowaną globalnie głębokość (`default_bars`, domyślnie 5000
świec) — i o `collect_from` nic nie wie. Dla `1D`/`4h`/`1W`, gdzie 5000 świec to lata, a nie
miesiące, archiwum skończyło z danymi od 2009, 2023 i 1991.

**Drugi: liczba świec nie jest granicą w czasie.** Po naprawie pierwszego ten sam test na żywo dał
ten sam objaw słabiej: dane nadal sięgały miesiące przed 2026-01-01. Licznik świec był naprawiony,
ale licznik świec nigdy nie był właściwym narzędziem. Kawałek zlecenia prosi gateway o `bars`
policzone jako **okresy kalendarza** w swoim oknie; gateway oddaje `bars` **świec**. Dla
instrumentu notowanego przez jakieś 70% czasu kalendarza te dwie liczby różnią się o połowę, więc
kawałek policzony na okno styczeń–sierpień dostawał świece sięgające jesieni poprzedniego roku
i zapisywał je. Tego nie da się naprawić lepszym licznikiem — trzeba nazwać starszą krawędź jako
moment.

**Trzeci, ujawniony przy naprawie drugiego: fałszywy „koniec historii".** Gdy odczyt dostał już
granicę w czasie, ostatnie okno stało się wąskie i przycięte do niej. Provider odpowiadał na nie
albo `error.prices.not-found`, albo tą samą świecą co poprzednio — a gateway czytał jedno i drugie
jako „instrument nie ma nic starszego". To stwierdzenie archiwum zapisuje jako trwałą granicę
i pomija na jego podstawie w hurcie każdy starszy kawałek stojący w kolejce. Zmierzone na żywo,
dwukrotnie, dwiema różnymi drogami wyjścia z tej samej pętli: kawałek `5m` na
2026-01-01 → 2026-02-16 skończył jako `skipped`, z zerem żądań, bo nowszy kawałek fałszywie
powiedział, że dalej nic nie ma. Sześć tygodni świec, o które operator poprosił, nie zostało nigdy
pobranych — a zlecenie pokazało `done`.

## What Changes

- `fill_gap` (a więc i `bars_to_close_gap`, którą woła) dla pary bez żadnej świecy MUST NOT sięgać
  dalej wstecz niż `collect_from` tej pary. Para dodana bez jawnej daty OD ma `collect_from`
  wyliczone z tej samej skonfigurowanej głębokości (`default_collect_from`), więc dla niej
  zachowanie się nie zmienia — zmienia się wyłącznie dla pary, której operator dał jawną, płytszą
  datę.
- Odczyt historii w gatewayu MUST przyjmować granicę w czasie, nie tylko liczbę świec: okna żądań
  przycinane do niej, stronicowanie zatrzymane na niej, świece starsze od niej odrzucone, zanim
  odpowiedź powstanie.
- Osiągnięcie granicy podanej przez wywołującego MUST NOT być raportowane jako koniec historii
  instrumentu — ani gdy przycięte okno wraca puste, ani gdy wraca bez niczego nowego. Obie drogi
  wyjścia z pętli stronicowania MUST rozstrzygać to jednym wspólnym warunkiem, bo rozjechały się
  raz i kosztowało to sześć tygodni danych.
- Obie ścieżki dociągania w `market-data` (kawałek zlecenia i cichy fill) MUST nazywać starszą
  krawędź jako moment i MUST NOT zapisać świecy starszej niż ona — także wtedy, gdy gateway
  odpowiedziałby czymś starszym. Obietnica o tym, co ląduje w archiwum, nie jest obietnicą do
  oddelegowania.
- Dwa niezależne mechanizmy dociągania wstecz (zlecenie i cichy fill) zostają nazwane wprost jako
  dwa mechanizmy, z jasną granicą, za co odpowiada który — decyzja, czy fill ma się w ogóle
  wstrzymać, gdy zlecenie już pokrywa parę, zapada w design.md, nie w tym proposalu.

## Capabilities

### New Capabilities

Brak.

### Modified Capabilities

- `market-data-ingest`: uzupełnianie wstecz dla pary bez żadnej świecy przestaje ignorować
  `collect_from` — scenariusz „Nowo dodana para" przestaje mówić „do skonfigurowanej głębokości"
  bez zastrzeżeń, bo to nie zawsze prawda.
- `capital-market-data`: głęboki odczyt zyskuje granicę w czasie obok liczby świec, a stwierdzenie
  „historia się skończyła" zostaje zawężone do tego, co powiedział provider — osiągnięcie granicy
  wywołującego przestaje się pod nie podszywać.
- `market-data-jobs`: kawałek zostaje ograniczony swoim oknem, nie tylko liczbą świec, a pomijanie
  starszych kawałków w hurcie zostaje związane wyłącznie z granicą providera.

## Impact

**capital-gateway**: `history.py` (`collect` — granica w czasie, przycinanie okien, jedno wspólne
rozstrzygnięcie dla obu wyjść z pętli), `adapter.py`, `app.py` (nowy parametr trasy `/history`),
README.

**market-data**: `ingest/backfill.py` (`bars_to_close_gap`, `fill_gap` — potrzebują odczytu
`collect_from` tej pary, którego dziś nie robią), `jobs/runner.py` (kawałek nazywa obie krawędzie
i filtruje, co zapisuje), `gateway/history.py` (przekazanie parametru), ewentualnie nowy lekki
odczyt w `tracking.py`.

**Zasięg**: `capital-gateway` i `market-data`. Terminal nie wie o `fill_gap` ani o kawałkach i nic
tu nie zmienia — kolumna „Data since", która to ujawniła, już działa poprawnie i pokazuje prawdę;
to backend miał dawać nieprawdziwe dane, nie terminal je źle czytał.

**Dane już w archiwum**: to nie jest migracja. Świece, które ten błąd już zebrał (jak w opisanym
przypadku US100), zostają — są prawdziwymi danymi z providera, tylko zebranymi bez pytania.
Operator, który chce się ich pozbyć, ma do tego `delete-archived-pair-data`.

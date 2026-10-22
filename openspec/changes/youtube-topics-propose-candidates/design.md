## Context

Dziś `ingest.py` w kroku *discover* robi z wynikami wyszukiwania tematu dokładnie to samo co z filmami kanału:
`store.upsert_films(...)` z pochodzeniem `topic:N` i promptem tematu. Dalej film idzie zwykłą drogą: transkrypcja,
odczyt, alert. Analizator (`analysis.py`, `OpenAIAnalyser`) ma jedno wywołanie modelu bez narzędzi, ze ścisłym
schematem JSON, liczone w `usage` i w `DAILY_TOKEN_LIMIT`. `VideoRef` nie niesie opisu filmu, choć `video_details`
już pobiera `snippet`, który go zawiera.

## Goals / Non-Goals

**Goals:**

- Gałąź tematów w *discover* pisze do `candidates`, nigdy do `videos`.
- Przesiew jest drugim, małym wywołaniem modelu z tą samą dyscypliną: brak narzędzi, ścisły schemat, dane obce
  oznaczone, koszt policzony.

**Non-Goals:**

- Zmiana drogi kanałów ani drogi filmu wskazanego ręcznie. „Analizuj film” woła istniejące `watchlist.analyse_film`.

## Decisions

**1. Osobna tabela `candidates`, a nie nowy stan w `videos`.**

`videos` ma stany, ponowienia, okno alertów i jest czytane przez listy, narzędzia i pakiet alertów. Kandydat w tej
tabeli musiałby być wykluczany w każdym z tych miejsc, a jedno przeoczenie oznacza transkrypcję, za którą nikt nie
chciał płacić. Przy osobnej tabeli przejście „kandydat → film” jest jawnym wywołaniem `analyse_film`.

Tabela niesie:

- `video_id` (PK);
- `topic_id` (nullable, bo temat można zdjąć);
- `phrase` (kopia frazy, żeby kandydat po zdjęciu tematu nadal mówił, skąd jest);
- metadane: tytuł, opis skrócony, kanał, data publikacji, długość;
- `found_at`;
- `verdict`: `proposed` | `rejected` | `unscreened`;
- `reason`, `screened_by` (model);
- `decision`: `null` | `dismissed` | `analysed` | `channel_followed` | `channel_ignored`, oraz `decided_at`.

Indeksy: `(found_at desc)` i `(published_at desc)` z warunkiem `decision is null`, bo domyślna lista czyta tylko
proponowanych bez decyzji. Koszt sprawdza skill `db-cost-check` przy implementacji.

`ignored_channels` to osobna tabela (`channel_id` PK, `channel_title`, `ignored_at`). Cofnięcie usuwa wiersz.

*Odrzucona alternatywa:* stan `candidate` w `videos`. Byłoby taniej w migracji, ale drożej w każdej przyszłej zmianie,
która czyta filmy.

**2. Jedno wywołanie przesiewu na wyszukiwanie, nie na film.**

Wyszukiwanie zwraca najwyżej `max_videos_per_run` wyników (domyślnie kilka). Jedno wywołanie z listą to jedna ramka
systemowa zamiast N. Odpowiedź to `{items: [{video_id, verdict, reason_pl}]}`. Element bez pasującego `video_id` albo
z niepoprawnym werdyktem daje kandydata `unscreened`. Nieudane wywołanie nie odbiera nikomu szansy: wszystkie wyniki
są wtedy `unscreened`.

*Odrzucona alternatywa:* wywołanie per film. Prostszy schemat, ale wielokrotność kosztu ramki i limitów zapytań.

**3. Brak przesiewu zapisuje kandydatów jako `unscreened` i proponuje ich, nie wstrzymuje.**

Kandydat nic nie kosztuje: archiwum go nie czyta. Wstrzymanie wyników do czasu, aż model będzie dostępny, wymagałoby
kolejki ponowień dla metadanych, które i tak się starzeją. Operator widzi oznaczenie „nieprzesiany” i ocenia sam.
`GET /state` mówi, dlaczego przesiew nie działa: brak klucza, odpoczynek po odmowie albo limit dnia.

**4. Odrzuceni przez model są zapisani.**

Dzięki temu operator może sprawdzić, czy przesiew nie wycina tego, czego szuka, a ten sam film z kolejnego
wyszukiwania nie jest przesiewany drugi raz. Bez zapisu każdy kolejny raz płacilibyśmy za ten sam werdykt.

**5. `Screener` to osobny protokół obok `Analyser`, z tym samym klientem OpenAI i modelem `YOUTUBE_ANALYSIS_MODEL`.**

Osobny protokół, bo wejście (lista metadanych z frazą) i wyjście (werdykty) nie mają nic wspólnego z odczytem
transkrypcji. Ten sam klient i model, bo nie ma powodu dokładać sekretu ani ustawienia. Symulacja dostaje
`SimScreener`: deterministyczny werdykt z danych scenariusza.

**6. Opis z `snippet.description` z wywołania `video_details`, przycięty do 1 000 znaków przed modelem.**

`video_details` już jest wołane dla każdego wyniku, więc opis nie kosztuje dodatkowej jednostki. Przycięcie ogranicza
tokeny: opisy YouTube bywają w większości linkami afiliacyjnymi.

**7. Wykluczenia przed przesiewem.**

Filmy już w archiwum, z kanałów obserwowanych, z kanałów ignorowanych i już będące kandydatami są odfiltrowane przed
wywołaniem modelu. Model płaci tylko za nowe.

**8. Decyzje „obserwuj kanał” i „ignoruj kanał” oznaczają też pozostałych kandydatów z tego kanału.**

Te decyzje dotyczą kanału, więc pozostali kandydaci z tego kanału bez decyzji dostają ją z tym samym momentem
(`channel_followed` / `channel_ignored`). Inaczej lista proponowałaby kanał, o którym już zdecydowano.

## Risks / Trade-offs

- **Reguły alertów z filtrem `topic` przestają dopasowywać nowe filmy.**
  → Skutek zamierzony, opisany w proposal. Przed wdrożeniem sprawdzić reguły na produkcji i powiedzieć o nich
  operatorowi.
- **Tabela `candidates` rośnie bez końca** (wiersz na każdy nowy wynik, także odrzucony). Przy suficie tematów i
  kilku wynikach na wyszukiwanie to tysiące wierszy w miesiącu, mało.
  → Bez retencji teraz. Wraca, jeśli `db-cost-check` albo `system-review` pokaże inaczej.
- **Model może wycinać wartościowe filmy.**
  → Odrzuceni są widoczni na żądanie, z uzasadnieniem.
- **Prompt injection przez tytuł i opis.**
  → Ta sama ramka „dane obce” co przy transkrypcji, ścisły schemat, brak narzędzi. Najgorszy skutek to zły werdykt,
  nie działanie.

## Migration Plan

Migracja `0004` w łańcuchu `youtube` biegnie w `lifespan` pod istniejącą blokadą `8110`:

- tworzy `candidates` i `ignored_channels` z uprawnieniami roli pakietu;
- zdejmuje `topics.prompt_id`.

Filmy z pochodzeniem `topic:N` zostają nietknięte. Te jeszcze w drodze (`discovered`, `transcribed`) kończą ją
normalnie, bo ich prompt jest zapisany na filmie.

`downgrade` przywraca `topics.prompt_id` z promptem zasianym i usuwa obie tabele. Kandydaci giną, bo nie da się ich
przenieść do starego świata.

Kolejność wdrożenia: najpierw workbench i kontrakt, potem terminal, w jednym PR, bo `contract:check` wiąże je w CI.

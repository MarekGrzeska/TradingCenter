## Context

Siedem drobiazgów, z których jeden — objętość danych per interwał — jest zmianą kontraktu i ciągnie
za sobą całą pięcioprzystankową trasę z `CLAUDE.md` („A new field on market-data's wire"). Reszta
mieszka wyłącznie w terminalu. Motywacja: proposal.md, „Why".

Stan wyjściowy, który kształtuje podejście:

- `_SELECT_STATUS` w `market_data/tracking.py` już robi `LEFT JOIN candles` i `GROUP BY` po parze,
  licząc `min`/`max(period_start)`. Liczba świec to dopisanie jednej agregacji do zapytania, które
  i tak biegnie — nie nowe zapytanie.
- `ESTIMATED_BYTES_PER_CANDLE = 96` żyje w `market_data/jobs/plan.py` i jest dziś prywatną sprawą
  wyceny zlecenia.
- Terminal trzyma czas wyłącznie jako sekundy od epoki (`terminal-market-data`, „Znaczniki czasu są
  sprowadzone do jednej postaci"), a wyświetla go w dwóch miejscach z osobna: `instruments/format.ts`
  (`formatInstant`) i jeden `toISOString()` wprost w `chart/Chart.tsx`.
- `RESOLUTION_ABBR` leży w `src/instruments/`, choć od tej zmiany potrzebują go też wykres i siatka.
- `lightweight-charts` 5.0.9 rysuje oś czasu w UTC i nie zna pojęcia strefy; udostępnia za to
  `timeScale.tickMarkFormatter` i `localization.timeFormatter`.

## Goals / Non-Goals

**Goals:**

- Jedna funkcja formatująca czas w całym terminalu i jedna tablica nazw interwałów — obie tam, gdzie
  sięgnie po nie i wykres, i Instruments, i historia dociągania.
- Liczba świec i objętość liczone przez archiwum, bez dodatkowego zapytania do bazy i bez migracji.
- Usunięcia (`forming`, wolumen, pokrycie w panelu, trzy zakładki) zabierają ze sobą swój kod
  i swoje testy, a nie zostawiają martwych gałęzi za flagą.

**Non-Goals:**

- Realny rozmiar danych w Postgresie. Szacunek wystarczy — patrz Decisions.
- Pełny zakres pokrycia (od–do) w rozwinięciu. Zostaje wyłącznie ostrzeżenie o lukach — patrz
  Decisions, „Rozwinięcie pyta o pokrycie tylko po to, żeby ostrzec o lukach".
- Wybór strefy przez operatora. Strefa jest jedna i wpisana na stałe.
- `Bar.forming` w danych. Zostaje — znika tylko jego rysowanie.

## Decisions

### Liczba świec dochodzi do zapytania, które już biegnie

`_SELECT_STATUS` dostaje `count(c.period_start) AS candle_count`. **Nie `count(*)`** — przy
`LEFT JOIN` `count(*)` liczy wiersze złączenia, więc para, która nie zebrała nic, dostałaby jedynkę
zamiast zera. To jedyna pułapka w tej linijce i jedyny powód, dla którego jest tu opisana.

Odrzucone: osobne `SELECT count(*) … WHERE symbol = $1 AND resolution = $2` per para — N zapytań na
każdy odczyt `/pairs`, który terminal odpytuje cyklicznie.

### Objętość to szacunek, liczony po stronie archiwum

`estimated_bytes = candle_count * ESTIMATED_BYTES_PER_CANDLE`. Stała przenosi się z `jobs/plan.py`
do `market_data/models.py`, obok `Candle`, i importują ją oba miejsca. Powód przeniesienia: to
własność wiersza świecy, a nie wyceny zlecenia, i od tej zmiany czyta ją ktoś jeszcze.

Dzięki jednej stałej „kreator obiecał 1,1 MB" i „Instruments pokazuje 1,1 MB" są tą samą liczbą —
gdyby terminal mnożył własnym mnożnikiem, rozjechałyby się przy pierwszej zmianie stałej.

Odrzucone: `sum(pg_column_size(c.*))` per para. Dokładne i bezużyteczne — pełny skan `candles` przy
każdym odczycie listy, rosnący z archiwum, dla liczby, którą operator i tak czyta jako „rząd
wielkości".

### Trasa nowego pola przez pięć przystanków

Zgodnie z `CLAUDE.md`: `tracking.py` (`TrackedPairStatus` + zapytanie) → `contract.py`
(`TrackedPairOut.candle_count`, `.estimated_bytes`) → `pnpm contract:generate` → `archive.ts`
(`mapTrackedPair`, snake→camel) → `types.ts` (`TrackedPair.candleCount`, `.estimatedBytes`) →
`InstrumentsView`. Przystanki 1 i 2 są tym, czego nic nie złapie automatycznie — pole dodane do
modelu domenowego i nie dodane do `*Out` po prostu nigdy nie wychodzi na drut.

Nazwa `estimated_bytes` celowo taka sama jak w `PairEstimateOut` — ta sama rzecz, ta sama nazwa.

### Rozwinięcie pyta o pokrycie tylko po to, żeby ostrzec o lukach

Liczba świec, objętość i moment początku przyjeżdżają razem z listą par — `IntervalCoverage` ich
już nie potrzebuje z `archive.coverage`. Wywołanie zostaje, bo jest jedynym źródłem informacji
o lukach (`ranges.length > 1`), ale jego wynik przestaje cokolwiek rysować poza tym jednym
przypadkiem: żadnego zakresu od–do, żadnej informacji o końcu historii u providera, i żadnego
stanu ładowania — pytanie jest w tle, a odpowiedź milczy, dopóki nie ma czego ostrzec.

Gdy `coverage.ranges.length > 1`: pokazany zostaje sam fakt luki, tak jak dziś („in N stretches,
with gaps between them"), bez zakresu dat wokół niej — zakres i tak nie byłby jednym ciągłym
przedziałem, więc podanie go razem z ostrzeżeniem nie dodaje nic ponad samo ostrzeżenie.

Gdy `coverage.ranges.length <= 1` (jeden ciągły przedział albo nic jeszcze niezweryfikowane):
rozwinięcie milczy o pokryciu. Napis „Nothing verified yet for this interval" znika z tego samego
powodu — interwał bez świec jest już nazwany przez liczbę świec równą zeru (ADDED „Rozwinięcie
instrumentu podaje objętość zebranych danych").

Błąd odczytu `archive.coverage` zostaje pokazany jak dotąd — cichy dla sukcesu, głośny dla
porażki.

### Strefa: formatowanie, nie przesuwanie znaczników

Jedna funkcja w `src/ui/formatTime.ts` (przeniesiony i przepisany `instruments/format.ts`), oparta
na `Intl.DateTimeFormat` z `timeZone: "Europe/Warsaw"` i `timeZoneName: "short"` → `2026-08-10 16:10
CEST`, zimą `CET`. DST załatwia `Intl`, nie my.

Dwie pułapki warte zapisania, bo obie kosztują jedno czerwone CI:

- `timeZoneName` **nie łączy się** z `dateStyle`/`timeStyle` — `Invalid option` w locie. Trzeba
  wypisać `year`/`month`/`day`/`hour`/`minute` osobno.
- Nazwa strefy zależy od locale: `en-GB` + `short` daje `CEST`, ale `shortGeneric` daje `CET`
  także latem. Locale i opcja są tu częścią kontraktu funkcji, a nie detalem.

Znaczniki świec MUST NOT być przesuwane o offset strefy — to sekundy od epoki, po których terminal
scala serie, deduplikuje świece i pyta archiwum o zakresy. Wykres dostaje strefę przez
`localization.timeFormatter` (etykieta krzyża) i `timeScale.tickMarkFormatter` (podpisy osi), oba
karmione tą samą funkcją.

Odrzucone: doliczenie offsetu do `bar.time` przed podaniem do wykresu. Zatruwa `mergeSeries`
i `findBar`, i rozjeżdża świecę ze strumienia ze świecą z historii dokładnie tam, gdzie
`terminal-market-data` wymaga, żeby trafiały w ten sam punkt.

### Nazwy interwałów w jednym pliku, poza `instruments/`

`RESOLUTION_ABBR` przenosi się do `src/ui/resolutionLabel.ts` z nowymi wartościami (`m1`, `m5`,
`m15`, `m30`, `h1`, `h4`, `day`, `week`) i staje się jedynym źródłem nazw — czyta go pole wyboru na
wykresie (dziś renderuje surowe `MINUTE_5`), Instruments, kreator i historia dociągania. Katalog
`ui/` dlatego, że to prezentacja wspólna dla kilku zakładek, a `instruments/` przestał być jej
właścicielem, gdy sięgnął po nią wykres.

### Zakładki znikają wraz z mechanizmem

Nie zostaje `TabStatus`/`ComingSoonTab` bez ani jednego wpisu. Znika `ComingSoon.tsx`, znika
rozgałęzienie w `App.tsx`, `TabDefinition` zostaje jednym kształtem z `Component`. `/positions`,
`/orders`, `/account` trafiają na `NotFound`, tak jak każdy inny nieznany adres.

## Risks / Trade-offs

- **Podziałka osi czasu wykresu wypada na granicach UTC, a podpisy są polskie.** `lightweight-charts`
  sam decyduje, który tick jest „nowym dniem", i robi to w UTC — więc na wykresie dziennym zmiana
  daty może wypaść o 02:00 czasu polskiego. → Podpisy są prawdziwe, więc data pod ticka jest
  właściwa; przesuwanie znaczników, które by to naprawiło, zatruwa scalanie serii (patrz Decisions).
  Zostaje jako znana niedoskonałość biblioteki, nie do obejścia w tej zmianie.
- **Szacunek objętości jest szacunkiem.** 96 B na świecę to nie to, co Postgres naprawdę zajmuje
  z indeksami i TOAST-em. → Liczba jest podana jako szacunek i jest tą samą liczbą, którą operator
  widział w kreatorze przed dociągnięciem, więc „obiecane" i „zebrane" da się porównać.
- **Data w kreatorze zmienia znaczenie.** Ten sam dzień wybrany w kalendarzu znaczy teraz północ
  warszawską, nie UTC — do dwóch godzin różnicy w tym, dokąd sięgnie dociągnięcie. → Różnica jest
  mniejsza niż jeden okres każdego interwału poza `m1`, a dla `m1` oznacza najwyżej 120 świec
  więcej; nic nie ginie, bo `collect_from` przy re-tracku idzie tylko wstecz.
- **Testy trzymają usuwane napisy.** `Chart.test.tsx` asertuje `forming` i wolumen,
  `InstrumentsView.test.tsx` pokrycie, `deployment.test.ts`/`App.test.tsx` zakładki. → Ich usunięcie
  jest częścią zadań, nie sprzątaniem po fakcie; test, który zniknął, jest w diffie widoczny.

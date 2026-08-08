## Context

Motywacja jest w [proposal.md](proposal.md) — tu tylko to, co ogranicza rozwiązanie.

Trzy fakty z kodu, wokół których wszystko się układa:

1. **`fill_gap` to jedno żądanie do gatewaya.** `backfill.py` liczy `bars_to_close_gap`, zamawia tyle
   świec jednym wywołaniem `/instruments/{symbol}/history` i to gateway stronicuje po tysiącu za tą
   jedną prośbą (`market-data-ingest`, „MUST NOT stronicować sam"). Z zewnątrz nie ma więc żadnego
   punktu pośredniego, z którego dałoby się odczytać postęp — jest przed i po. Każdy procent
   liczony dziś byłby zmyślony.
2. **`FillOutcome` żyje w pamięci `Ingest`.** `ingest.last_fill(symbol, resolution)` to słownik w
   procesie, jeden wpis na parę, nadpisywany. Restart go czyści, a wcześniejszych uzupełnień nie ma
   nigdzie poza logiem.
3. **Katalog gatewaya jest ucinany obchodem.** `list_instruments(max_nodes=300)` chodzi po drzewie
   providera i zwraca `truncated`, kiedy się zatrzyma. Kaskada „klasa → instrument" karmiona takim
   katalogiem pokazywałaby kilkanaście krypto z kilkuset i wyglądała na kompletną.

Do tego ograniczenie, którego nie wolno naruszyć: gateway przepuszcza **dziesięć żądań na sekundę na
całe konto**, dzielone z ruchem interaktywnym terminala i z nasłuchem na żywo. Głębokie dociąganie
to dziesiątki takich żądań pod rząd.

## Goals / Non-Goals

**Goals:**

- Postęp, który jest pomiarem, a nie animacją — na tyle drobnoziarnisty, żeby operator widział ruch
  w ciągu kilku minut, i na tyle gruboziarnisty, żeby nie kosztował dodatkowych żądań.
- Jeden komponent podpowiedzi w terminalu, obsługujący trzy zastosowania, których jedyną różnicą
  jest źródło pozycji.
- Zmiana kontraktu `market-data`, przy której dotychczasowy konsument `POST /pairs` nie pęka.
- Porażka pojedynczego kawałka zostawia archiwum w stanie, który potrafi się sam opisać (pokrycie
  z luką) i sam naprawić (ponowienie).

**Non-Goals:**

- Kolejka zadań na zewnętrznym brokerze. Zlecenia są w tej samej bazie co świece i wykonuje je ten
  sam proces co ingest.
- Anulowanie zlecenia w trakcie. Zdjęcie pary zatrzymuje jej kawałki; osobnej operacji „anuluj
  zlecenie" nie ma.
- Estymacja z kalendarzem sesji. Szacunek liczy okresy kalendarzowe i mówi, że jest szacunkiem.
- Zmiana sposobu, w jaki wykres czyta świece. Subskrypcja archiwum zostaje bez zmian.

## Decisions

### Kawałek to para i okno czasu, a nie strona odpowiedzi

Zlecenie rozkłada się na kawałki `(symbol, rozdzielczość, od, do)`, gdzie okno mieści
`MAX_BARS_PER_FILL` świec danej rozdzielczości. Kawałek jest **jednym** wywołaniem odczytu historii —
czyli tym, czym jest dzisiaj jeden fill — więc reguła „moduł nie stronicuje sam" zostaje
nienaruszona: to nadal gateway dzieli okno kawałka na strony po tysiąc.

**Odkryte podczas implementacji, nie przewidziane przy planowaniu:** `GET
/instruments/{symbol}/history` w `capital-gateway` dziś zawsze kotwiczy się na chwili bieżącej —
`history.collect()` zaczyna pierwszą stronę od `(None, None)`, co provider czyta jako „najnowsze N
świec". Nie ma jak zażądać okna leżącego w przeszłości, więc kawałek okna `(od, do)` sprzed
miesięcy nie miał czym się wykonać. `capital-gateway` dostaje więc dodatkowy parametr `before`
(`GET /instruments/{symbol}/history?before=...`), który zastępuje `(None, None)` pierwszej strony
kotwicą podaną przez wywołującego; dalsze stronicowanie wstecz działa jak dotychczas, kotwicząc
się na najstarszej pobranej świecy. Kawałek zamawia się jako `before=chunk_end`, `bars` policzone z
`(chunk_end - chunk_start)` — patrz nowe wymaganie w `capital-market-data`, „Głęboki odczyt zaczyna
się w dowolnym momencie, nie tylko teraz".

Postęp zlecenia to `kawałki ukończone / kawałki wszystkie`. Dla `MINUTE` i 50 000 świec na kawałek
jedno okno to ~35 dni, więc dziesięć lat historii minutowej to ~104 kawałki — pasek rusza się co
kilkadziesiąt sekund. Dla `DAY` całe dziesięć lat mieści się w jednym kawałku i pasek skacze z 0 na
100, co jest uczciwe: nie ma tam nic pośredniego do pokazania.

*Rozważone i odrzucone:* strumień postępu z gatewaya (SSE albo WebSocket raportujący strony) —
dawałby ładniejszy pasek kosztem nowego kanału w kontrakcie gatewaya, nowego stanu po obu stronach i
tego, że postęp znikałby przy zerwaniu połączenia. Nie warte tego, żeby liczba rosła płynniej.

### Nieudany kawałek nie wywraca zlecenia, a ponowienie bierze tylko jego

Kawałek zapisuje świece przez `write_candles` i `record_coverage`, i to zostaje. „Wycofanie
zlecenia" byłoby udawanym rollbackiem — archiwum z zasady nie kasuje danych
(`market-data-tracking`, „Usunięcie zatrzymuje zbieranie, ale nie kasuje danych"), więc jedyne, co
dałoby się cofnąć, to zamiar. Luka po nieudanym kawałku jest reprezentowalna: `coverage_ranges`
trzyma listę przedziałów i panel już dziś mówi „w N przedziałach, z lukami między nimi".

Ponowienie wybiera kawałki ze stanem `failed` albo `interrupted` i wykonuje wyłącznie je, w ramach
tego samego zlecenia — nowa próba, nie nowe zlecenie. Dzięki temu Data History pokazuje jedną
pozycję z historią prób, a nie serię wpisów bez związku.

*Rozważone i odrzucone:* zatrzymanie zlecenia na pierwszym błędzie. Jeden odrzucony zakres u
providera zabierałby wtedy także kawałki, które by przeszły, a operator i tak musiałby zlecić to
ponownie — z tą różnicą, że od zera.

### Zlecenia i kawałki idą do bazy `market-data`

Nowa migracja `0005_collection_jobs.py`: `collection_jobs` (kto, kiedy, jaka data OD, stan) i
`collection_job_chunks` (para, okno, stan, świece zapisane, przyczyna porażki, numer próby). Stan
zlecenia jest **wyprowadzany** ze stanów kawałków, a nie trzymany osobno — dwa źródła prawdy o tym
samym rozjeżdżają się dokładnie wtedy, gdy proces ginie między zapisem jednego a drugiego.

Start modułu przestempluje na `interrupted` kawałki zostawione w stanie `running` **i** `pending` —
runner nie przeżywa restartu, więc kawałek czekający w kolejce jest tak samo osierocony jak ten w
trakcie żądania do gatewaya; różni je tylko to, że jeden zdążył wysłać żądanie, a drugi nie. To
zamyka scenariusz „zlecenie przerwane zatrzymaniem" bez żadnego zegara ani heartbeatu: proces, który
działa, jest jedynym, który może mieć kawałek w toku, i po jego starcie nic w bazie nie udaje, że coś
się dzieje samo.

*Rozważone i odrzucone:* trzymanie tego w pamięci i dopisanie do zakładki zdania „historia od
ostatniego startu". Zakładka nazywa się Data History i po restarcie byłaby pusta akurat wtedy, kiedy
operator najbardziej chce wiedzieć, co się dociągnęło.

### Wycena liczy kawałki, a nie osobną formułę

`POST /jobs/estimate` przechodzi tę samą drogę co tworzenie zlecenia — przycięcie daty OD do
`earliest_reachable`, odjęcie tego, co pokrywa `coverage_ranges`, podział na okna — i zwraca liczbę
kawałków, sumę świec i rozmiar. Nie tworzy niczego. Dzięki temu dialog akceptacji pokazuje **tę
samą** pracę, którą akceptacja uruchomi, a nie drugie przybliżenie liczone innym wzorem.

Liczba świec to okresy kalendarzowe w przyciętym zakresie (`PERIOD_SECONDS`), więc dla rynku
zamkniętego w weekendy jest zawyżona — dialog mówi to wprost. Rozmiar to liczba świec razy stała
bajtów na wiersz, opisana jako przybliżenie. Kalendarz sesji dałby dokładniejszą liczbę kosztem
żądania na instrument przy każdym otwarciu dialogu; szacunek zawyżony jest tu bezpieczniejszy od
dokładnego, bo operator podejmuje na jego podstawie decyzję o koszcie.

### Data OD jest przycinana, nigdy odrzucana

Rok 1850 to nie błąd walidacji, tylko „daj wszystko". Przycięcie idzie do
`coverage.earliest_reachable`, gdy jest znane, a gdy nie jest — do domyślnej głębokości z
konfiguracji, i pierwszy kawałek sięgający końca historii providera ustawia `history_ended`, po czym
dalsze kawałki wstecz są pomijane jako bezprzedmiotowe (nie jako nieudane). Odrzucana jest wyłącznie
data w przyszłości, bo ta nie znaczy nic.

### Terminal: jeden `Autocomplete`, trzy źródła

`src/ui/Autocomplete.tsx` jest sterowany propem `source: (query, signal) => Promise<Option[]>` i nie
wie, skąd biorą się pozycje. Trzy zastosowania różnią się wyłącznie tym propem: klasy aktywów
(zbiór stały, filtrowany lokalnie), instrumenty w klasie (gateway), instrumenty archiwizowane
(`/pairs`, grupowane po symbolu). Debounce i ochrona przed wyprzedzającą się odpowiedzią przenoszą
się z `useInstrumentSearch` do wspólnego haka — logika już istnieje i jest przetestowana, zmienia
się tylko to, kto ją woła.

`SymbolField` w slocie siatki przestaje być `<input>` i staje się tym komponentem ze źródłem
„archiwizowane". To domyka pętlę, którą dziś zamyka komunikat błędu: zamiast pozwolić wpisać
cokolwiek i wyjaśnić po fakcie, że tego nikt nie zbiera, terminal po prostu tego nie oferuje.

### Zakładki: `Archive` znika, `Data History` dochodzi

`TABS` w `src/app/tabs.ts` traci wpis `archive`, a `instruments` dostaje widok będący połączeniem
obu. Dochodzi `data-history`. Rejestr jest otwarty (`terminal-shell`, „Rejestr zakładek jest
otwarty"), więc pasek i routing wynikają z tej listy i nie wymagają dotknięcia. Adres `/archive`
trafia na istniejącą stronę „nie ma takiej zakładki" — świadomie, bez przekierowania, bo cicha
podmiana adresu pod zakładką przeglądarki jest gorsza od jawnego „to się przeniosło".

Wiersz listy jest per instrument. Grupowanie `/pairs` po symbolu robi terminal — kontrakt oddaje
pary, bo parą jest to, co archiwum śledzi, i nie ma powodu, żeby kształt widoku przeciekał do
kontraktu.

### Filtr klasy w gatewayu, z osobnym pułapem obchodu

`GET /instruments?asset_class=CRYPTO` odsiewa po klasie w trakcie obchodu drzewa, z pułapem
`max_nodes` podniesionym dla zapytania z filtrem (jedna klasa to ułamek katalogu, więc ten sam
budżet węzłów sięga w niej znacznie dalej). `truncated` zostaje i nadal znaczy to samo. Dochodzi
`GET /asset-classes`, żeby pierwszy autocomplete nie miał zaszytej listy, która rozjedzie się z
providerem.

*Rozważone i odrzucone:* grupowanie po stronie terminala z jednego pobrania katalogu. Tańsze o
zmianę w gatewayu, ale operator wybierałby instrument do archiwizowania z listy uciętej — decyzja
kosztująca dziesiątki minut dociągania podjęta na niepełnych danych.

## Risks / Trade-offs

- **Zlecenie na dziesięć lat minutowych to ~104 żądania do gatewaya** → kawałki idą pod istniejącym
  `backfill_concurrency` (domyślnie 1) i tym samym rate gate co reszta; dialog akceptacji pokazuje
  liczbę kawałków, więc koszt jest widoczny **przed** decyzją, a nie po niej.
- **Postęp dla `DAY`/`WEEK` skacze 0 → 100** → uczciwe, ale wygląda jak zawieszenie. Zakładka
  pokazuje obok procentu parę właśnie obsługiwaną, więc widać, że coś się dzieje.
- **Odpytywanie co 30 s przy wielu zleceniach** → odczyt idzie do własnej bazy, nie do gatewaya, i
  jest jednym zapytaniem na całą zakładkę. Odpytywanie ustaje przy opuszczeniu zakładki.
- **Szacunek zawyżony dla rynków z weekendem** → opisany jako szacunek; po zakończeniu Data History
  pokazuje liczbę faktyczną, więc rozjazd jest widoczny i wyjaśniony, a nie zaskakujący.
- **`SymbolField` przestaje przyjmować symbol z ręki** → operator znający symbol traci najszybszą
  drogę. Podpowiedzi filtrują po wpisanej frazie, więc wpisanie symbolu i Enter nadal działa —
  różnica jest taka, że musi trafić w coś archiwizowanego.
- **Zapamiętany slot z instrumentem zdjętym z archiwizowanych** → slot rozpoznaje to przy starcie i
  mówi wprost, zamiast wpadać w pętlę wznawiania połączenia, którą dziś rozstrzyga `whyRefused`.
- **`POST /pairs` zmienia kształt** → pole daty OD jest opcjonalne, a żądanie w starej postaci
  zachowuje dotychczasowe znaczenie. Test kontraktowy pilnuje starej postaci.

## Migration Plan

1. Migracja `0005_collection_jobs.py` dokłada dwie tabele i kolumnę `collect_from` do
   `tracked_pairs`. Kolumna wypełnia się dla istniejących wierszy z `added_at` minus domyślna
   głębokość — czyli tym, co i tak było ich faktycznym zobowiązaniem.
2. `market-data` i `capital-gateway` wchodzą przed terminalem: nowe endpointy są dokładane, żaden
   istniejący nie zmienia znaczenia, więc terminal sprzed zmiany działa dalej na tym backendzie.
3. Terminal wchodzi jako całość — połączona zakładka, `Data History` i podpowiedzi w slocie są
   jedną zmianą UI i rozdzielenie ich zostawiłoby stan pośredni, w którym zakładki mówią o sobie
   nawzajem rzeczy nieprawdziwe.
4. Wycofanie: cofnięcie terminala wystarcza, bo backend pozostaje zgodny wstecz. Migracji nie
   trzeba cofać — tabele zleceń są dokładane, nie przerabiane, a `collect_from` ma wartość dla
   każdego istniejącego wiersza.

## Context

Świece trzyma `market-data`, rysuje je `terminal`, a `capital-gateway` jest dla przeglądarki
nieosiągalny — jego katalog instrumentów jedzie do terminala proxy przez archiwum. Oba wdrożone
kontenery stoją na jednym planie App Service B1 z jednym workerem, a próg alertu pamięci tego planu
podniesiono niedawno do 92%. To są warunki brzegowe, w których trzeba było wybrać miejsce obliczeń.

Motywacja i zakres: `proposal.md`. Wymagania: `specs/`. Podstawa techniczna:
`docs/wskazniki-techniczne.html` (research) i `docs/wskazniki-plan-wdrozenia.html` (plan etapów).

## Goals / Non-Goals

**Goals:**

- Jedna implementacja matematyki, po stronie serwera, dla wszystkich przyszłych konsumentów —
  terminala, backtestów i modułu strategii.
- Dodanie kolejnego wskaźnika ma być tanie: zmiana w jednym pliku po stronie modułu i zero zmian
  w terminalu, dopóki kształt wyjścia i sposób rysowania już istnieją.
- Granica wobec strategii wymuszona kształtem kontraktu, a nie dyscypliną autora.

**Non-Goals:**

- Wydajność ponad ustalony sufit żądania. Sufit jest odpowiedzią, nie optymalizacja.
- Wskaźniki zależne od stanu (Parabolic SAR, SuperTrend, ZigZag, Renko, Kagi). Odłożone świadomie,
  patrz decyzja niżej.
- Wysunięcie linii w przyszłość (Ichimoku, Alligator). Odłożone razem z Ichimoku, patrz niżej.

## Decisions

### Obliczenia w `market-data`, nie w nowym module

Rozważone: (a) nowy moduł `analytics`, (b) obliczenia w terminalu w TypeScripcie, (c) funkcje
okienkowe w PostgreSQL, (d) nowy obszar w `market-data`.

Wybrane (d), z czterech powodów, z których żaden nie jest estetyczny. Przeglądarka nie dosięgnie
trzeciego adresu bez trzeciej konfiguracji Easy Auth, CORS-a i wpisu w konfiguracji terminala.
Plan B1 nie ma miejsca na trzeci kontener `always_on` — to zmiana SKU, czyli koszt. Osobny moduł
musiałby ciągnąć świece po HTTP, bo nie wolno mu sięgnąć do cudzej bazy, a idą one w obie strony
przy każdym żądaniu. Precedens jest w module: `rollups.py` też liczy na własnej serii.

Odrzucone (b), bo agenty i backtesty nic by z tego nie miały, a druga implementacja tej samej
matematyki w Pythonie unieważniłaby obietnicę powtarzalności. Odrzucone (c), bo rekurencja w SQL
to `WITH RECURSIVE` albo PL/pgSQL, a wersjonowanie wzoru staje się wtedy migracją.

Cena: opis modułu jako „archiwum świec" przestaje wystarczać. Do poprawienia w `CLAUDE.md` przy tej
samej zmianie: archiwum odpowiada na pytania o serię, której jest właścicielem.

Furtka wyjściowa wpisana w projekt: jądro liczące nie importuje ani FastAPI, ani asyncpg. Bierze
listy liczb, oddaje listy liczb. Wyniesienie go później do osobnego modułu jest przeniesieniem
katalogu i napisaniem nowego routera, a nie przepisywaniem matematyki.

### Własne jądro na `numpy`, TA-Lib wyłącznie jako wyrocznia testowa

Rozważone: TA-Lib w runtimie, `pandas-ta`, `ta`, `talipp`, własne.

Wybrane własne, bo determinizm jest tu produktem, a każda z bibliotek ma własną konwencję zasiewu
i własny „unstable period", których nie da się nadpisać per wywołanie. TA-Lib dokłada zależność od
biblioteki C w obrazie; `pandas-ta` nie jest utrzymywane; `ta` jest za wąskie; `talipp` jest
stanowe, czyli akurat to, czego ten kontrakt unika.

Cały zestaw stoi na ~20 prymitywach (`sma`, `ema`, `rma`, `wma`, `stdev`, `true_range`,
`rolling_max/min`, `rolling_argmax/argmin`, `linreg`, `mean_abs_dev`, `shift`, `diff`, `cross`).
RSI to `rma` dwóch strumieni, ATR to `rma(true_range)`, ADX to `rma` na `rma`, Keltner to
`ema ± m·atr`. TA-Lib wchodzi jako zależność `dev` i służy do porównania z jawną tolerancją oraz
spisaną listą znanych różnic — różnica zasiewu nie jest błędem żadnej ze stron.

Jedyna nowa zależność runtime: `numpy`.

### Rozgrzewka jako próg tłumienia, nie jako umówiona wielokrotność

Rozważone: stała wielokrotność okresu (np. 5·n), zasiew umowny udokumentowany w kontrakcie, próg
tłumienia.

Wybrany próg tłumienia: `m = ceil(ln(1e-9) / ln(1 − α))`, co daje ok. `10·(n+1)` dla EMA i ok.
`21·n` dla wygładzania Wildera. Powód jest praktyczny: zamienia obietnicę „zasiewamy tak samo",
którą łatwo złamać przy refaktorze, we własność matematyczną — wpływ punktu startu jest poniżej
precyzji odczytu — a ta daje się przetestować jednym testem dla wszystkich wskaźników naraz.

Serwer sam rozszerza okno odczytu wstecz i mówi w odpowiedzi, dokąd sięgnął. Alternatywa, w której
robi to konsument, wymagałaby, żeby znał regułę rozgrzewki każdego wskaźnika.

### Wyniki nie są przechowywane

Rozważone: tabela wyników odświeżana przyrostowo, jak `derived_candles`.

Odrzucone, bo przestrzeń kluczy jest nieograniczona: rollup jest jeden na parę i rozdzielczość,
a wskaźnik ma parametry — EMA(9), EMA(21), EMA(37), bo ktoś tak kliknął. Determinizm sprawia, że
przeliczenie jest tanie i zawsze zgodne. Efekt uboczny jest znaczny: żadnej migracji, żadnej
inwalidacji przy backfillu, żadnego wzrostu bazy.

### Katalog jako dane, nie jako typy

Rozważone: wygenerowany typ per wskaźnik w kontrakcie terminala.

Odrzucone, bo wtedy każdy nowy wskaźnik dotyka terminala i przechodzi całą pięcioprzystankową
ścieżkę zmiany kontraktu. Katalog jest listą wpisów o wspólnym kształcie; typowana jest koperta,
nie zawartość. Terminal typuje kształt wpisu i sposoby rysowania, których obsługę ma napisaną.

### Cztery kształty wyjścia od pierwszego etapu

Etap pierwszy produkuje tylko linie. Mimo to `markers`, `zones` i `levels` istnieją w modelach od
początku, bo dołożenie kolejnego wariantu do opublikowanej odpowiedzi jest zmianą łamiącą, a strefy
przychodzą już w czwartym etapie.

### Granica wobec strategii wymuszona kontraktem

Nie wystarczy jej zapisać. Trzy rzeczy w kontrakcie sprawiają, że przekroczenie jej jest widoczne:
linia nie może być wartością logiczną, każdy próg jest parametrem żądania powtórzonym
w odpowiedzi, a nazwy jednej szkoły siedzą w polu z nazwami potocznymi, nie w identyfikatorach.
Dzięki temu `range_gap` z nazwą potoczną „FVG" jest jednym wpisem, a nie dwoma bytami.

### Sufit żądania zamiast odciążania wątkiem

Rozważone: `run_in_executor`, `scipy.signal.lfilter`, sufit.

Wątek nie pomoże — pętla rekurencyjna w Pythonie trzyma GIL, więc strumień świec i tak stanie.
`scipy` pomogłoby (ten sam wzór w C, zwalnia GIL), ale to ~35 MB w obrazie kupione przed pomiarem.
Wybrany sufit na iloczynie świec i linii plus semafor na obliczeniach; `scipy` wraca do rozważenia,
gdy pomiar z zadania 1.1 pokaże, że jest potrzebne.

### Wskaźniki zależne od stanu i wysunięte w przyszłość — poza tą zmianą

Parabolic SAR, SuperTrend, ZigZag i serie przebudowane (Renko, Kagi) nie mają tłumienia, tylko stan:
dociągnięcie starszej historii zmienia ich dzisiejszą wartość. Da się to zrobić uczciwie — przez
jawną kotwicę w odpowiedzi — ale to osobna kategoria z własnym wymaganiem i własnym sposobem
testowania, i nie ma powodu wiązać jej z tą zmianą.

Ichimoku i Alligator odpadają z innego powodu: ich linie są przesunięte o kilkadziesiąt świec
w przyszłość, a narysowanie tego wymaga znaczników czasu, których nikt tu nie zna. Terminal celowo
nie zna długości okresu, `PERIOD_SECONDS` jest dla `DAY` i `WEEK` jawnie nadmiarowym przybliżeniem,
a `market_status` wie tylko, czy rynek jest otwarty teraz — nie zna kalendarza sesji. Arytmetyka na
stałej długości okresu wyprowadziłaby linię w weekend. Wracają, gdy w systemie pojawi się kalendarz
sesji.

### Realizacja przyrostowa na jednej gałęzi

Jedna zmiana, sześć etapów, gałąź `add-technical-indicators`. Każdy etap wchodzi na nią osobno,
z własnymi testami; do `main` trafia całość, po lokalnym przetestowaniu i review. Powód: kontrakt
i katalog ustalają się w etapie zerowym i przez kolejne etapy jeszcze się układają — wypuszczanie
ich do `main` po kawałku znaczyłoby publikowanie kontraktu, o którym wiadomo, że się zmieni.

## Risks / Trade-offs

- **Obliczenia dzielą pętlę zdarzeń ze strumieniem świec** → sufit żądania i semafor od pierwszego
  etapu; pomiar p95 przed rozrostem katalogu; `scipy` albo osobny moduł jako droga odwrotu, dla
  której jądro jest już przygotowane.
- **Katalog rozjeżdża się z jądrem** — wpis deklaruje linię, której obliczenie nie zwraca, i nic
  tego nie wykrywa → jeden test liczący *każdy* wpis katalogu na krótkiej serii i porównujący klucze
  wyjścia z deklaracją. Wchodzi w etapie zerowym, nie później.
- **Zmiana wzoru bez podniesienia wersji** → pliki wzorcowe pokazują diff przy każdej zmianie
  wartości, więc podniesienie wersji jest widoczne w tym samym commicie.
- **Rozmiar odpowiedzi** — 20 linii po 5000 punktów to około megabajta JSON-a → zmierzyć po
  kompresji przed jakąkolwiek optymalizacją; kompresja jest po stronie App Service.
- **Terminal wąskim gardłem** — Python gotowy, ale nie ma czym narysować → prymityw rysowania jest
  częścią zakresu etapu, w którym pojawia się jego kształt, a nie osobną „integracją po".
- **Rozlanie zakresu katalogu** → lista pozycji jest zamknięta w `tasks.md`; kolejne wskaźniki są
  osobnymi, tanimi zmianami, i właśnie po to katalog jest danymi.
- **Głębokość archiwum** — ADX(14) potrzebuje ~580 świec rozgrzewki, czyli ponad dwóch lat na
  serii dziennej → moduł mówi o tym wprost (`settled`), zamiast podawać wartość jako pewną.

## Migration Plan

Brak migracji bazy i brak zmian w `infra/`. Wdrożenie to nowy obraz `market-data` i nowy build
terminala; wycofanie to `revert` — nie ma stanu, który zostałby po zmianie.

Kolejność w każdym etapie dotykającym kontraktu: modele w `market_data/contract.py`, potem
`pnpm contract:generate` w terminalu, dopiero potem kod terminala. CI uruchamia job terminala przy
każdej zmianie `contract.py`, więc pominięcie kroku środkowego zatrzyma się na `contract:check`.

## Open Questions

- Konkretna wartość sufitu żądania. Ustalona po pomiarze w etapie zerowym; kształt odmowy jest już
  określony w spec, więc zmiana samej liczby nie rusza ani kontraktu, ani zadań.
- Domyślna szerokość kubełka w profilu czasowym — ułamek ATR czy wielokrotność kroku instrumentu.
  Rozstrzygalna przy etapie profilu, na danych.
- Czy dopytywanie o ogon po zamknięciu świecy wystarczy, czy potrzebna będzie subskrypcja
  wskaźników. Odpowiedź po zmierzeniu opóźnienia na działającym stosie; obie drogi mieszczą się
  w tym samym kontrakcie.

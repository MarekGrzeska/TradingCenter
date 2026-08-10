## Purpose

Trzyma świece, które przeleciały strumieniem albo zostały dociągnięte z historii, i wie o sobie
tyle, żeby odróżnić okres, w którym rynek był zamknięty, od okresu, którego po prostu nie zebrał.
## Requirements
### Requirement: Świecę identyfikuje symbol, rozdzielczość i początek okresu

Archiwum MUST identyfikować świecę trójką: symbol, rozdzielczość, znacznik czasu początku okresu.
Dla jednej trójki MUST istnieć najwyżej jedna świeca. Powtórny zapis tej samej trójki MUST
nadpisać wpis, a nie dołożyć drugi.

#### Scenario: Ta sama świeca przychodzi dwa razy

- **WHEN** ingest zapisuje świecę o symbolu, rozdzielczości i początku okresu już obecnych
  w archiwum
- **THEN** archiwum trzyma nadal dokładnie jedną świecę tego okresu
- **AND** odczyt zakresu nie zwraca powtórzonego znacznika czasu

#### Scenario: Odczyt zachowuje porządek

- **WHEN** konsument odczytuje zakres świec
- **THEN** dostaje je uporządkowane od najstarszej

### Requirement: Zapisywana jest wyłącznie świeca zamknięta

Świeca w budowie zmienia się przy każdym kwotowaniu i po restarcie źródła zaniża swój zakres.
Archiwum MUST NOT utrwalać świecy oznaczonej jako w budowie. Trafia do niego wyłącznie świeca
zamknięta.

Reguła obowiązuje niezależnie od tego, którą drogą świeca przyszła. Odczyt historii sięgający
chwili bieżącej zwraca także okres, który jeszcze trwa, i taka świeca MUST NOT zostać
utrwalona tak samo jak ta ze strumienia — archiwum MUST NOT zakładać, że wszystko, co
przyszło z historii, jest zamknięte. Cena jest tu wyższa niż przy strumieniu, bo świeca
utrwalona z historii zatrzymuje kolejne uzupełnianie: zaległość liczy się od najnowszej
posiadanej świecy, więc bieżący okres zapisany jako fakt wygląda jak archiwum, które jest na
bieżąco, i zostaje z częściowymi wartościami do czasu, aż postarzeje się o dwa okresy.

#### Scenario: Strumień niesie świecę w budowie

- **WHEN** ze strumienia przychodzi świeca oznaczona jako w budowie
- **THEN** archiwum nie zapisuje jej
- **AND** świeca pozostaje dostępna konsumentom jako wartość ulotna, nieutrwalona

#### Scenario: Odczyt historii niesie okres, który jeszcze trwa

- **WHEN** odczyt historii zwraca świecę oznaczoną jako należącą do okresu, który się nie
  domknął
- **THEN** archiwum nie zapisuje jej, a zapisuje pozostałe świece z tego samego odczytu
- **AND** zakres pokrycia obejmuje okres tak samo jak dotąd, bo został sprawdzony

#### Scenario: Okres się zamyka

- **WHEN** dla okresu, który był w budowie, przychodzi świeca zamknięta
- **THEN** archiwum zapisuje wartości ze świecy zamkniętej

### Requirement: Wartość od providera jest autorytatywna

Ta sama świeca może dotrzeć dwiema drogami — ze strumienia oraz z uzupełniania wstecz. Gdy wartości
się różnią, archiwum MUST zachować tę pochodzącą z odczytu historii providera, bo strumień mógł
przegapić kwotowania w czasie przerwy w połączeniu.

#### Scenario: Uzupełnianie wstecz trafia na świecę ze strumienia

- **WHEN** uzupełnianie wstecz przynosi świecę okresu zapisanego wcześniej ze strumienia
- **THEN** archiwum zastępuje wartości tymi z odczytu historii

#### Scenario: Strumień trafia na świecę z uzupełniania

- **WHEN** ze strumienia przychodzi zamknięta świeca okresu pochodzącego z odczytu historii
- **THEN** archiwum zachowuje wartości już zapisane

### Requirement: Jedna strona ceny w całym archiwum

Świece MUST być przechowywane po tej samej stronie ceny, której używa `capital-gateway`, czyli po
stronie bid. Strona ceny MUST być zapisana wprost przy danych, a nie dorozumiana, żeby dołożenie
kiedyś drugiej strony nie zmieszało obu w jednej serii.

#### Scenario: Odczyt nazywa stronę ceny

- **WHEN** konsument odczytuje świece
- **THEN** odpowiedź stwierdza, po której stronie ceny są zbudowane

### Requirement: Archiwum wie, co pokrywa

Brak świecy o 3:00 w sobotę i brak świecy, bo ingest nie działał, wyglądają w danych identycznie.
Archiwum MUST przechowywać dla każdej śledzonej pary zakresy czasu, dla których dane zostały
zweryfikowane, żeby te dwa przypadki dało się rozróżnić.

Granica „provider nie ma nic starszego" jest częścią tego zapisu i kosztuje więcej niż reszta:
na jej podstawie moduł pomija pracę, do której sam z siebie nigdy nie wróci. Dlatego MUST być
zapisana tam, gdzie dane faktycznie się skończyły — na najstarszej świecy, którą odczyt przyniósł
— a nie na krawędzi okna, o które zapytano. Te dwa punkty dzieli wszystko, czego provider nie
miał, a zapisanie tego drugiego ogłasza jako sprawdzone coś, czego nikt nie sprawdził.

Granica MUST przestać obowiązywać, gdy ktoś jawnie prosi o dane starsze od niej. Historia
u providera z czasem się pogłębia, zapis mógł powstać z odpowiedzi, która nie znaczyła tego, co
się jej przypisało, a operator proszący o wcześniejszą datę wyraża dokładnie jedno: żeby
sprawdzić to jeszcze raz. Archiwum MUST wtedy zdjąć granicę i zaplanować pełny zakres, MUST NOT
zaś przyciąć prośby po cichu do wartości, którą trzyma. Samo odczytanie stanu pokrycia ani wycena
pracy MUST NOT zdejmować granicy — robi to wyłącznie ścieżka, która faktycznie zleca zbieranie.

#### Scenario: Brak świecy wewnątrz pokrycia

- **WHEN** w zweryfikowanym zakresie nie ma świecy dla danego okresu
- **THEN** archiwum stwierdza, że rynek był wtedy zamknięty, a nie że brakuje danych

#### Scenario: Brak świecy poza pokryciem

- **WHEN** żądany okres wypada poza jakimkolwiek zweryfikowanym zakresem
- **THEN** archiwum stwierdza, że tego okresu nie zebrało

#### Scenario: Historia instrumentu się skończyła

- **WHEN** uzupełnianie wstecz dochodzi do miejsca, w którym provider nie ma starszych danych
- **THEN** jako najstarsza możliwa granica pokrycia zostaje zapisany znacznik czasu najstarszej
  świecy, którą ten odczyt przyniósł
- **AND** kolejne uzupełnianie nie sięga już przed tę granicę

#### Scenario: Odczyt kończy się bez ani jednej świecy

- **WHEN** odczyt sięgający wstecz nie przynosi żadnej świecy
- **THEN** archiwum MUST NOT zapisać dla tej pary granicy najstarszego osiągalnego momentu
- **AND** zakres pozostaje możliwy do zebrania przy kolejnej próbie

#### Scenario: Prośba o dane starsze niż zapisana granica

- **WHEN** zlecenie zbierania jest tworzone dla pary z datą początku wcześniejszą niż zapisana
  granica najstarszego osiągalnego momentu
- **THEN** archiwum zdejmuje tę granicę i planuje cały żądany zakres
- **AND** granica zostaje zapisana na nowo dopiero wtedy, gdy provider potwierdzi ją ponownie

#### Scenario: Odczyt stanu pokrycia nie zmienia granicy

- **WHEN** konsument odczytuje stan pokrycia pary albo prosi o wycenę pracy z datą początku
  wcześniejszą niż zapisana granica
- **THEN** granica pozostaje zapisana bez zmian
- **AND** wycena pokazuje ten sam zakres, który zostałby zaplanowany, gdyby zlecenie powstało

### Requirement: Rozdzielczości pochodne są wyliczane, nie pobierane

Provider oddaje najwyżej tysiąc świec na żądanie i jest ograniczony do dziesięciu żądań na sekundę,
więc pobieranie ośmiu rozdzielczości osobno kosztuje ośmiokrotność ruchu. Archiwum MUST wyliczać
rozdzielczości o stałej długości okresu z serii minutowej. `DAY` i `WEEK` MUST pochodzić
z providera, bo ich granica zależy od sesji rynku, a nie od zegara.

#### Scenario: Odczyt rozdzielczości pochodnej

- **WHEN** konsument prosi o świece w rozdzielczości wyliczalnej z serii minutowej
- **THEN** dostaje serię zbudowaną z otwarcia pierwszej świecy okresu, maksimum i minimum
  wszystkich oraz zamknięcia ostatniej

#### Scenario: Rozdzielczość dzienna albo tygodniowa

- **WHEN** konsument prosi o świece dzienne albo tygodniowe
- **THEN** archiwum oddaje wartości pochodzące z providera, a nie wyliczone z serii minutowej

#### Scenario: Okres niepełny

- **WHEN** dla okresu rozdzielczości pochodnej archiwum ma tylko część świec minutowych
- **THEN** wyliczona świeca stwierdza, że powstała z niepełnego okresu

### Requirement: Skasowanie danych pary zdejmuje też jej pokrycie

Zakres pokrycia jest zapisem tego, że dane dla danego przedziału zostały zweryfikowane. Po usunięciu
świec taki zapis mówi nieprawdę i, co gorsza, jest wiążący dla planowania: przedział uchodzący za
pokryty nie zostanie pobrany ponownie. Archiwum MUST usuwać świece pary i jej zakresy pokrycia
razem, w jednej niepodzielnej operacji — MUST NOT być stanu pośredniego, w którym pokrycie przeżyło
świece, ani takiego, w którym świece przeżyły pokrycie.

Skasowanie MUST dotyczyć wyłącznie wskazanej pary (symbol i rozdzielczość) — dane innych
archiwizowanych rozdzielczości tego samego symbolu MUST zostać nietknięte, bo każda z nich jest
osobną decyzją operatora.

Wyjątkiem są świece wyliczone z serii kasowanej: są jej projekcją, a nie osobno zebranymi danymi.
Skasowanie serii, z której zostały wyliczone, MUST usunąć je razem z nią — inaczej archiwum
odpowiadałoby na pytanie o rozdzielczość pochodną danymi, których źródło operator kazał usunąć.

#### Scenario: Skasowanie danych pary

- **WHEN** dane pary zostają skasowane
- **THEN** ani jedna świeca tej pary nie pozostaje w archiwum
- **AND** ani jeden zakres pokrycia tej pary nie pozostaje w archiwum

#### Scenario: Kasowanie przerwane w połowie

- **WHEN** kasowanie danych pary nie może dojść do końca
- **THEN** archiwum zostaje w stanie sprzed kasowania
- **AND** MUST NOT zostać para bez świec, ale z zachowanym pokryciem

#### Scenario: Zapytanie o okres po skasowaniu

- **WHEN** konsument pyta o okres, który przed skasowaniem był pokryty
- **THEN** archiwum stwierdza, że tego okresu nie zebrało
- **AND** MUST NOT stwierdzać, że rynek był wtedy zamknięty

#### Scenario: Inna rozdzielczość tego samego symbolu

- **WHEN** zostaje skasowana jedna rozdzielczość symbolu archiwizowanego w kilku
- **THEN** świece i pokrycie pozostałych archiwizowanych rozdzielczości tego symbolu zostają
  nietknięte

#### Scenario: Skasowanie serii, z której wyliczane są inne

- **WHEN** zostaje skasowana seria, z której archiwum wylicza rozdzielczości pochodne tego symbolu
- **THEN** wyliczone z niej świece również przestają istnieć
- **AND** zapytanie o rozdzielczość pochodną tego symbolu MUST NOT odpowiadać danymi wyliczonymi
  przed skasowaniem


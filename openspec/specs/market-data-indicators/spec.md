# market-data-indicators Specification

## Purpose

Wskaźniki techniczne liczone na serii, której archiwum jest właścicielem: ta sama para,
rozdzielczość i zakres dają zawsze tę samą wartość. Moduł podaje miary i geometrię, a nie
werdykty — próg stawia ten, kto podejmuje decyzję.
## Requirements
### Requirement: Wskaźnik jest czystą funkcją świec

Wartość wskaźnika MUST zależeć wyłącznie od świec i parametrów wskazanych w żądaniu. Obliczenie
MUST NOT sięgać po zegar, losowość ani ustawienia regionalne, a kolejność operacji
zmiennoprzecinkowych MUST być ustalona, żeby dwa przebiegi nie różniły się ostatnim bitem.

Moduł MUST NOT zaokrąglać wyników. Zaokrąglenie należy do prezentacji, bo zależy od instrumentu
i jest nieodwracalne.

#### Scenario: Dwa identyczne odczyty

- **WHEN** ten sam zakres tej samej pary zostaje odczytany dwa razy, a archiwum się nie zmieniło
- **THEN** obie odpowiedzi niosą identyczne wartości

#### Scenario: Odczyt po restarcie modułu

- **WHEN** moduł zostaje zrestartowany i zapytany o ten sam zakres
- **THEN** wartości są takie same jak przed restartem

### Requirement: Rozgrzewka jest wyliczona, jawna i niezależna od punktu startu

Dla wskaźnika rekurencyjnego moduł MUST odczytać świece wcześniejsze niż początek żądanego zakresu
w liczbie, przy której wpływ pierwszej próbki spada poniżej `1e-9`. Odpowiedź MUST podawać, dokąd
odczyt naprawdę sięgnął, oraz MUST mówić, czy wartości w zwróconym zakresie są już ustabilizowane.

Wartość dla tego samego okresu MUST NOT zależeć od tego, od którego momentu konsument poprosił
o serię.

#### Scenario: Ten sam okres w dwóch różnych zakresach

- **WHEN** ten sam okres zostaje odczytany raz w zakresie tygodniowym, raz w miesięcznym
- **THEN** wartość wskaźnika dla tego okresu jest w obu odpowiedziach taka sama

#### Scenario: Archiwum płytsze niż rozgrzewka

- **WHEN** archiwum nie ma tylu wcześniejszych świec, ile wymaga rozgrzewka
- **THEN** odpowiedź mówi, że wartości nie są jeszcze ustabilizowane
- **AND** podaje najstarszy okres, do którego odczyt sięgnął

#### Scenario: Okresy przed rozgrzewką

- **WHEN** dla okresu nie da się jeszcze policzyć wartości
- **THEN** odpowiedź niesie dla niego wartość nieznaną, a MUST NOT zera ani żadnej wartości zastępczej

### Requirement: Katalog wystarcza do zbudowania wybieraka

Moduł MUST publikować katalog wskaźników, a wpis katalogu MUST nieść wszystko, czego konsument
potrzebuje, żeby zaoferować ten wskaźnik i narysować go bez wiedzy o nim: identyfikator, nazwę,
grupę, przyjmowane parametry z zakresami i wartościami domyślnymi, kształt wyjścia oraz podpowiedź
sposobu rysowania.

Wpis MAY nieść nazwy potoczne, pod którymi wskaźnik jest znany, żeby wyszukiwanie działało po tym,
czego operator faktycznie używa, a kontrakt nie musiał przyjmować słownictwa jednej szkoły.

Dodanie wskaźnika o kształcie wyjścia i sposobie rysowania już obecnym w katalogu MUST NOT wymagać
zmiany po stronie konsumenta.

#### Scenario: Konsument buduje listę

- **WHEN** konsument odczytuje katalog
- **THEN** ma dość informacji, by pokazać każdy wskaźnik z jego parametrami i wartościami domyślnymi

#### Scenario: Wyszukiwanie po nazwie potocznej

- **WHEN** operator szuka wskaźnika po nazwie potocznej, innej niż jego identyfikator
- **THEN** wskaźnik zostaje znaleziony

#### Scenario: Nowy wskaźnik w istniejącym kształcie

- **WHEN** do katalogu dochodzi wskaźnik zwracający linie, tak jak wskaźniki już obecne
- **THEN** pojawia się u konsumenta bez żadnej zmiany po jego stronie

### Requirement: Katalog mierzy, a nie orzeka

Wskaźnik MUST zwracać miarę albo obiekt geometryczny, a MUST NOT zwracać wartości logicznej
wyliczonej z progu. Gdy definicja wymaga progu, próg MUST być parametrem żądania, a odpowiedź MUST
go powtarzać — nigdy nie MAY zostać ukryty jako stała wewnątrz obliczenia.

Powód: próg jest decyzją konsumenta. Zaszyty we wskaźniku sprawia, że zmiana zdania o handlu
wymaga wydania nowej wersji modułu danych.

#### Scenario: Miara zamiast rozstrzygnięcia

- **WHEN** konsument pyta o skalę ruchu świecy
- **THEN** dostaje zakres świecy wyrażony w jednostkach zmienności
- **AND** MUST NOT dostać informacji, czy ruch był wystarczająco duży

#### Scenario: Próg podany w żądaniu

- **WHEN** wskaźnik z definicji potrzebuje progu, na przykład tolerancji skupiska poziomów
- **THEN** próg jest parametrem żądania i wraca w odpowiedzi razem z wynikiem

### Requirement: Wskaźnik liczy się z jednej serii świec

Obliczenie MUST korzystać wyłącznie z otwarcia, maksimum, minimum i zamknięcia świec jednej pary
w jednej rozdzielczości. Katalog MUST NOT zawierać wskaźnika czytającego wolumen ani wskaźnika
wymagającego drugiego instrumentu.

Wolumen odpada, bo w tym archiwum jest strukturalnie nieobecny: świeca ze strumienia go nie niesie,
więc świeca pochodna prawie zawsze ma go pustego, a wskaźnik dawałby wtedy inną odpowiedź zależnie
od rozdzielczości.

#### Scenario: Katalog bez wolumenu

- **WHEN** konsument przegląda katalog
- **THEN** nie ma w nim wskaźnika, którego wejściem jest wolumen

#### Scenario: Świeca z wolumenem od źródła

- **WHEN** świece w zakresie niosą wolumen
- **THEN** żadne obliczenie go nie używa

### Requirement: Jedno żądanie liczy wiele wskaźników na wspólnej osi czasu

Moduł MUST przyjmować w jednym żądaniu listę wskaźników z parametrami i MUST odpowiadać jedną osią
znaczników czasu wspólną dla wszystkich wyników. Odpowiedź MUST powtarzać parametry każdego
wskaźnika, żeby dwa warianty tego samego wskaźnika dały się rozróżnić.

Wyniki MUST wracać w kolejności zamówionych wskaźników — n-ty wynik odpowiada n-temu zamówieniu,
także wtedy, gdy dwa zamówienia mają ten sam identyfikator i te same parametry, i także wtedy, gdy
któreś z nich wraca z przyczyną zamiast wartości. Identyfikator i parametry same w sobie MUST NOT
być jedynym sposobem powiązania wyniku z zamówieniem, bo nie odróżniają zamówień identycznych.

#### Scenario: Kilka wskaźników naraz

- **WHEN** konsument prosi o kilka różnych wskaźników dla jednego zakresu
- **THEN** dostaje je w jednej odpowiedzi, ułożone na jednej osi czasu

#### Scenario: Ten sam wskaźnik z różnymi parametrami

- **WHEN** konsument prosi dwa razy o ten sam wskaźnik z różnymi parametrami
- **THEN** dostaje dwa osobne wyniki, każdy z powtórzonymi parametrami

#### Scenario: Kolejność wyników

- **WHEN** konsument zamawia kilka wskaźników w wybranej przez siebie kolejności
- **THEN** wyniki wracają w tej samej kolejności, po jednym na każde zamówienie

#### Scenario: Dwa identyczne zamówienia

- **WHEN** konsument zamawia dwa razy ten sam wskaźnik z tymi samymi parametrami
- **THEN** dostaje dwa wyniki, na pierwszej i drugiej pozycji odpowiadających tym zamówieniom

### Requirement: Wynik ma jeden z czterech kształtów

Wynik wskaźnika MUST mieć dokładnie jeden z czterech kształtów: wartości na świecę, zdarzenia
w punktach, strefy cenowe albo poziomy. Wpis katalogu MUST zapowiadać, którego z nich użyje.

Wynik, którego nie dało się policzyć, MUST wrócić bez żadnego z czterech kształtów, za to
z nazwaną przyczyną. MUST być odróżnialny od wyniku policzonego pusto: brak stref to stwierdzenie,
że w tym zakresie żadnej nie było, i MUST NOT być tym samym, co niemożność ich policzenia. Wynik
z przyczyną MUST NOT być pominięty w odpowiedzi — konsument, który zamówił wskaźnik, MUST dostać
w odpowiedzi wpis o nim, cokolwiek się z nim stało.

Strefa MUST nieść granice cenowe, moment powstania i — gdy jest już zamknięta — moment zakończenia,
a także fakty o tym, czy i kiedy cena do niej weszła. Fakty te MUST dotyczyć wyłącznie żądanego
zakresu: strefa nietknięta do końca zakresu MUST NOT być opisana jako nietknięta w ogóle.

#### Scenario: Strefa wciąż otwarta

- **WHEN** strefa nie została domknięta do końca żądanego zakresu
- **THEN** odpowiedź mówi, że jej koniec jest nieustalony, zamiast podawać koniec zakresu jako koniec strefy

#### Scenario: Kształt zapowiedziany w katalogu

- **WHEN** konsument czyta wpis katalogu przed wywołaniem obliczenia
- **THEN** wie, którego z czterech kształtów się spodziewać

#### Scenario: Wynik bez kształtu, za to z przyczyną

- **WHEN** zamówionego wskaźnika nie dało się policzyć
- **THEN** wraca on w odpowiedzi z nazwaną przyczyną i bez żadnego z czterech kształtów

#### Scenario: Pusto policzony a niepoliczalny

- **WHEN** konsument porównuje wskaźnik, który nie znalazł w zakresie ani jednej strefy, ze wskaźnikiem, którego nie dało się policzyć
- **THEN** odróżnia jedno od drugiego, zamiast widzieć w obu pustą listę

### Requirement: Odpowiedź niesie to, czego archiwum nie pokrywa

Odpowiedź MUST powtarzać stwierdzone przez archiwum odcinki żądanego zakresu, których nigdy nie
zweryfikowano, w tej samej postaci, w jakiej podaje je odczyt świec. MUST także mówić, po której
stronie ceny liczone są świece i czy seria była wyliczona z serii minutowej, czy zebrana wprost.

Wskaźnik policzony w poprzek dziury w danych wygląda tak samo jak policzony na danych pełnych,
a znaczy co innego — i tylko konsument wie, czy może na to przystać.

#### Scenario: Zakres z niepokrytym odcinkiem

- **WHEN** żądany zakres obejmuje odcinek, którego archiwum nigdy nie zweryfikowało
- **THEN** odpowiedź go wymienia obok wyników

#### Scenario: Seria pochodna

- **WHEN** wskaźnik liczony jest na rozdzielczości wyliczanej z serii minutowej
- **THEN** odpowiedź mówi, że seria jest pochodna

### Requirement: Obliczenie obejmuje wyłącznie świece zamknięte

Obliczenie MUST pomijać okres, który jeszcze się nie zamknął. Świeca w budowie zmienia się z każdym
kwotowaniem i zaniża własny zakres, więc wskaźnik z niej policzony byłby wartością, która sama się
cofa.

#### Scenario: Bieżący okres

- **WHEN** żądany zakres sięga chwili obecnej, a bieżący okres jeszcze trwa
- **THEN** ostatnia zwrócona wartość dotyczy ostatniego zamkniętego okresu

### Requirement: Zbyt duże żądanie zostaje odrzucone

Moduł MUST odmówić obliczenia, gdy iloczyn liczby świec i liczby zamówionych wyników przekracza
ustalony sufit, i MUST nazwać w odmowie granicę, o którą chodzi. Odmowa MUST być odróżnialna od
awarii: powtórzenie tego samego żądania da tę samą odpowiedź.

Sufit istnieje, bo obliczenia dzielą proces ze strumieniem świec i jedno nieograniczone żądanie
zatrzymałoby subskrypcje wszystkich odbiorców.

#### Scenario: Żądanie ponad sufit

- **WHEN** konsument prosi o więcej, niż pozwala sufit
- **THEN** dostaje odmowę nazywającą przekroczoną granicę, a nie obciętą odpowiedź

#### Scenario: Zakres odwrócony

- **WHEN** koniec żądanego zakresu jest wcześniejszy niż jego początek
- **THEN** moduł odmawia, zamiast zwracać pustą serię

### Requirement: Brakująca seria nie unieważnia policzonych wskaźników

Gdy część zamówionych wskaźników nie da się policzyć z powodu tego, czego archiwum nie ma,
a pozostałe da się, moduł MUST odpowiedzieć: policzone wracają policzone, niepoliczone wracają
z przyczyną. Taka odpowiedź MUST być odpowiedzią udaną, a MUST NOT być odmową.

Granica jest tu świadoma i przebiega po tym, czyj to problem. Brak serii nie jest pomyłką
wołającego — jest właściwością tego, co ktoś zdecydował się zbierać, i różni się wskaźnik po
wskaźniku. Pomyłka wołającego jest inna: nieznany identyfikator wskaźnika, parametr poza
zakresem katalogu, zakres kończący się przed swoim początkiem i żądanie ponad sufit MUST nadal
być odmową całego żądania. Cicha, częściowa odpowiedź na literówkę w identyfikatorze
przeszłaby niezauważona, a odmowa nie przechodzi.

#### Scenario: Jeden wskaźnik bez serii, reszta policzona

- **WHEN** konsument zamawia jednym żądaniem wskaźnik wymagający serii, której archiwum nie ma, oraz wskaźniki liczone z serii rysowanej
- **THEN** dostaje odpowiedź, w której te drugie są policzone, a pierwszy niesie nazwany brak

#### Scenario: Wszystkie zamówione wskaźniki bez serii

- **WHEN** żadnego z zamówionych wskaźników nie da się policzyć z powodu brakujących serii
- **THEN** odpowiedź nadal jest odpowiedzią i niesie przyczynę przy każdym z nich, zamiast być odmową

#### Scenario: Nieznany identyfikator obok policzalnych wskaźników

- **WHEN** konsument zamawia jednym żądaniem wskaźnik o identyfikatorze, którego katalog nie zna, oraz wskaźniki policzalne
- **THEN** moduł odmawia całego żądania, zamiast odpowiadać częściowo

#### Scenario: Parametr poza zakresem obok policzalnych wskaźników

- **WHEN** konsument zamawia jednym żądaniem wskaźnik z parametrem poza zakresem podanym w katalogu oraz wskaźniki policzalne
- **THEN** moduł odmawia całego żądania i mówi, jaki zakres obowiązuje

#### Scenario: Powtórzenie tego samego żądania

- **WHEN** konsument powtarza żądanie, na które dostał odpowiedź częściową, przy niezmienionym archiwum
- **THEN** dostaje tę samą odpowiedź, z tymi samymi przyczynami przy tych samych wskaźnikach

### Requirement: Zmiana wzoru jest widoczna w odpowiedzi

Katalog i każda odpowiedź MUST nieść wersję zestawu algorytmów. Zmiana sposobu liczenia
któregokolwiek wskaźnika MUST podnosić tę wersję.

Bez tego dwa wdrożenia rysują z tych samych danych inny wykres i nie da się powiedzieć, od kiedy.

#### Scenario: Porównanie dwóch odpowiedzi

- **WHEN** konsument porównuje odpowiedzi otrzymane w różnym czasie
- **THEN** po wersji poznaje, czy liczone były tak samo

### Requirement: Punkt zwrotny potwierdza się z opóźnieniem i już się nie zmienia

Punkt zwrotny MUST być zgłaszany dopiero wtedy, gdy potwierdziła go wymagana liczba świec po nim,
a odpowiedź MUST podawać, ile tych świec potrzeba. Raz zgłoszony punkt zwrotny MUST NOT zniknąć ani
przesunąć się przy późniejszym odczycie tego samego zakresu.

Opóźnienie jest uczciwe i wystarcza; cofanie się wstecz nie jest i wykluczyłoby użycie do decyzji.

#### Scenario: Świeży skrajny punkt

- **WHEN** ostatnia świeca jest ekstremum, ale nie ma po niej dość świec, by je potwierdzić
- **THEN** punkt zwrotny nie jest jeszcze zgłaszany

#### Scenario: Powtórny odczyt

- **WHEN** ten sam zakres zostaje odczytany później, gdy przybyło świec
- **THEN** wcześniej zgłoszone punkty zwrotne są w tych samych miejscach

### Requirement: Poziomy z wyższego interwału pochodzą z zamkniętego okresu

Poziomy wyprowadzone z rozdzielczości wyższej niż rysowana — ekstrema i otwarcia poprzedniego
okresu — MUST pochodzić z okresu, który się już zamknął, i MUST obowiązywać od jego zamknięcia,
a nie od początku serii.

Gdy archiwum nie ma dla pary serii w wymaganej rozdzielczości, moduł MUST nazwać brak przy tym
wskaźniku, a MUST NOT zwracać poziomów wyliczonych z rozdzielczości zastępczej. Brak ten
MUST NOT unieważniać pozostałych wskaźników tego samego żądania.

#### Scenario: Poziomy poprzedniego dnia na wykresie minutowym

- **WHEN** konsument prosi o poziomy dnia poprzedniego dla serii piętnastominutowej
- **THEN** dostaje je jako poziomy obowiązujące od zamknięcia tamtego dnia

#### Scenario: Brak serii w wymaganej rozdzielczości

- **WHEN** para nie jest archiwizowana w rozdzielczości, z której poziomy miałyby pochodzić
- **THEN** wynik tego wskaźnika niesie nazwany brak zamiast poziomów

### Requirement: Przerwa w handlu nie jest luką cenową

Wykrywanie luk cenowych MUST odróżniać lukę powstałą w handlu od przerwy między sesjami,
rozpoznanej po pokryciu archiwum, a nie po kształcie samych świec. Domyślnie moduł MUST NOT
zgłaszać przerwy sesyjnej jako luki cenowej.

Na kontraktach CFD przerwa weekendowa układa się w podręcznikową lukę na każdym instrumencie
i w każdy weekend, więc bez tego rozróżnienia zgłoszenia byłyby w większości fałszywe.

#### Scenario: Weekend

- **WHEN** zakres obejmuje piątkowe zamknięcie i niedzielne otwarcie
- **THEN** przerwa między nimi nie jest zgłaszana jako luka cenowa

#### Scenario: Luka wewnątrz sesji

- **WHEN** luka powstaje między świecami wewnątrz otwartej sesji
- **THEN** zostaje zgłoszona

### Requirement: Okno sesji liczy się w zadanej strefie czasowej

Okna czasowe MUST przyjmować strefę czasową jako parametr, a ich granice MUST być wyznaczane
w kalendarzu tej strefy. Moduł MUST NOT wyznaczać ich przez dodanie stałego przesunięcia do czasu
uniwersalnego.

Strefy przestawiają zegar w różne weekendy, więc stałe przesunięcie daje poprawny wynik przez
większość roku i cichy błąd przez resztę.

#### Scenario: Okno po zmianie czasu

- **WHEN** to samo okno sesji liczone jest przed i po zmianie czasu w zadanej strefie
- **THEN** w obu przypadkach obejmuje te same godziny lokalne

### Requirement: Profil czasowy liczy się z serii minutowej

Rozkład czasu spędzonego przy cenie MUST być liczony z serii minutowej pary, także wtedy, gdy
zamówiony jest dla rozdzielczości wyższej. Odpowiedź MUST podawać rozkład, poziom o największym
udziale oraz przedział obejmujący zadany udział całości.

Gdy para nie ma serii minutowej, moduł MUST nazwać brak przy tym wskaźniku, a MUST NOT zwracać
profilu policzonego z grubszej serii. Brak ten MUST NOT unieważniać pozostałych wskaźników tego
samego żądania.

#### Scenario: Profil pod wykresem czterogodzinnym

- **WHEN** konsument prosi o profil dla serii czterogodzinnej
- **THEN** profil jest policzony z minut, a nie z czterogodzinnych świec

#### Scenario: Para bez serii minutowej

- **WHEN** para jest archiwizowana wyłącznie w rozdzielczości godzinowej
- **THEN** wynik profilu niesie nazwany brak zamiast rozkładu


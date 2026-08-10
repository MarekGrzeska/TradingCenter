## Purpose

Podaje, czym jest instrument i co robił: znajdowanie instrumentów, którymi da się handlować, oraz
odczyt ich historii świecowej — łącznie z historią głębszą niż zwraca jedno żądanie do providera.
## Requirements
### Requirement: Instrumenty są wyszukiwalne i wyliczalne

Moduł MUST pozwalać znaleźć instrumenty po frazie oraz wyliczyć cały katalog. Każdy instrument
MUST nieść symbol, nazwę, klasę aktywów i informację, czy da się nim handlować. Wyliczenie katalogu
MUST dać się zawęzić do jednej klasy aktywów, a wynik zawężony MUST obejmować wszystkie instrumenty
tej klasy — konsument wybierający z takiej listy podejmuje decyzję na podstawie tego, co widzi, więc
lista ucięta ograniczeniem obchodu byłaby dla niego gorsza niż brak listy. Moduł MUST podać zbiór
klas aktywów, jakimi opisuje instrumenty.

#### Scenario: Wyszukiwanie po frazie

- **WHEN** konsument wyszukuje frazę
- **THEN** moduł zwraca pasujące instrumenty z symbolem, nazwą, klasą aktywów, flagą
  handlowalności oraz bieżącym bid i ask tam, gdzie provider je podaje

#### Scenario: Wyliczenie katalogu

- **WHEN** konsument wylicza instrumenty
- **THEN** wynik nie zawiera zduplikowanych symboli
- **AND** stwierdza, czy obchód został ucięty własnym ograniczeniem, żeby katalog częściowy nigdy
  nie został wzięty za kompletny

#### Scenario: Wyliczenie jednej klasy aktywów

- **WHEN** konsument wylicza instrumenty, wskazując klasę aktywów
- **THEN** wynik obejmuje wyłącznie instrumenty tej klasy
- **AND** nie jest ucięty ograniczeniem obchodu, dopóki klasa mieści się w skonfigurowanym pułapie
  dla zapytania z filtrem

#### Scenario: Klasa aktywów spoza znanych

- **WHEN** konsument wskazuje klasę aktywów, której moduł nie zna
- **THEN** moduł odmawia i wylicza klasy, które zna

#### Scenario: Odczyt zbioru klas aktywów

- **WHEN** konsument pyta o klasy aktywów
- **THEN** dostaje zbiór klas, jakimi moduł opisuje instrumenty

#### Scenario: Gałąź katalogu jest nieczytelna

- **WHEN** części katalogu nie da się odczytać
- **THEN** ta część jest pomijana, a reszta zwracana, zamiast wywrócić cały odczyt

### Requirement: Świece czyta się w zadanej rozdzielczości

Moduł MUST podawać świece instrumentu w zadanej rozdzielczości, od najstarszej, bez powtórzonych
znaczników czasu. Wspierane rozdzielczości MUST obejmować `MINUTE`, `MINUTE_5`, `MINUTE_15`,
`MINUTE_30`, `HOUR`, `HOUR_4`, `DAY` i `WEEK`.

#### Scenario: Odczyt bieżących świec

- **WHEN** konsument prosi o świece instrumentu w danej rozdzielczości
- **THEN** odpowiedź jest uporządkowana od najstarszej, nie zawiera powtórzonego znacznika czasu
  i podaje rozdzielczość na każdej świecy

#### Scenario: Nieznany symbol

- **WHEN** konsument prosi o świece symbolu, którego provider nie zna
- **THEN** moduł odpowiada błędem „nie znaleziono" nazywającym symbol

### Requirement: Wszędzie ta sama strona ceny

Świece MUST być budowane ze strony bid kwotowań providera, zarówno w historii, jak i w danych na
żywo, żeby seria złożona z obu była ciągła.

#### Scenario: Historia styka się z danymi na żywo

- **WHEN** konsument dokleja świece odebrane na żywo do świec historycznych tego samego symbolu
- **THEN** obie strony mają tę samą konwencję cenową i szew nie wprowadza skoku

### Requirement: Historia jest stronicowana poza limit providera

Provider zwraca najwyżej 1000 świec na żądanie i odrzuca okno czasowe szersze niż żądana liczba.
Moduł MUST stronicować wstecz, żeby zaspokoić większe żądanie, a każde kolejne okno MUST być
kotwiczone na najstarszej już pobranej świecy, a nie na zegarze — rynek, który był zamknięty,
zwraca mniej świec, niż wynika z kalendarza.

Konsument MUST móc ograniczyć odczyt nie tylko liczbą świec, ale i momentem, poniżej którego nie
chce zejść. Liczba tego nie wyraża i wyrazić nie może: liczba liczy świece, a instrument zamknięty
przez pół tygodnia oddaje żądaną liczbę świec z okresu znacznie dłuższego niż tyle samo okresów
kalendarza — „nic starszego niż 1 stycznia" nie jest zdaniem, które da się powiedzieć licznikiem.
Gdy konsument poda taki moment, moduł MUST przyciąć do niego okna żądań, żeby nie wydawać żądania
na świece z góry przeznaczone do odrzucenia, MUST zatrzymać stronicowanie po jego osiągnięciu
i MUST NOT zwrócić ani jednej świecy starszej niż on.

Stwierdzenie „historia się skończyła" mówi o providerze, nie o konsumencie. MUST paść wyłącznie
wtedy, gdy provider nie ma nic starszego, i MUST NOT paść dlatego, że odczyt zatrzymał się na
granicy, którą konsument sam podał — o tym, co provider trzyma poniżej tej granicy, taki odczyt
nie dowiedział się niczego. Rozróżnienie jest kosztowne w jedną stronę: konsument zapisuje to
stwierdzenie jako trwałą granicę instrumentu i pomija na jego podstawie pracę, do której nigdy
potem nie wróci.

Ta sama cena obowiązuje w drugą stronę: stwierdzenie MUST NOT paść na podstawie okna, z którego
moduł nie zebrał ani jednej świecy. Odmowa danych dla pierwszego okna odczytu nie odróżnia „nic
starszego nie ma" od „na to konkretne okno nie dostałem odpowiedzi" — provider odpowiada brakiem
danych także wtedy, gdy okno wypada poza godzinami, których nie zna, albo gdy odpytany jest
o instrument chwilowo bez notowań. Koniec historii MUST być stwierdzony wyłącznie tam, gdzie
odczyt zdążył zejść po danych: dopiero okno kotwiczone na świecy, którą ten odczyt już trzyma,
mówi coś o tym, co leży pod nią.

#### Scenario: Prośba o więcej świec, niż mieści jedno żądanie

- **WHEN** konsument prosi o więcej świec, niż provider podaje w jednym żądaniu
- **THEN** moduł wysyła tyle żądań, ile trzeba, i zwraca jedną serię, uporządkowaną od najstarszej
  i wolną od powtórzonych znaczników czasu

#### Scenario: Historia instrumentu się kończy

- **WHEN** stronicowanie dochodzi do miejsca, w którym provider nie ma starszych danych
- **THEN** moduł zatrzymuje się i zwraca to, co zebrał, co nie jest błędem
- **AND** odpowiedź stwierdza, że seria jest krótsza od żądanej, bo historia się skończyła

#### Scenario: Okno nie przynosi nic nowego

- **WHEN** kolejne okno nie daje świecy starszej niż najstarsza już posiadana
- **THEN** stronicowanie kończy się, zamiast powtarzać to samo okno

#### Scenario: Pierwsze okno odczytu nic nie przynosi

- **WHEN** provider odpowiada brakiem danych na pierwsze okno odczytu, więc moduł nie zebrał
  jeszcze ani jednej świecy
- **THEN** odczyt kończy się i zwraca pustą serię, co nie jest błędem
- **AND** odpowiedź MUST NOT stwierdzać, że historia instrumentu się skończyła

#### Scenario: Odczyt ograniczony momentem, nie liczbą

- **WHEN** konsument prosi o świece do chwili bieżącej, podając moment, poniżej którego nie chce
  zejść, i liczbę świec większą, niż ten okres faktycznie mieści
- **THEN** moduł stronicuje wstecz tylko do tego momentu, a nie do wyczerpania żądanej liczby
- **AND** odpowiedź MUST NOT zawierać świecy starszej niż podany moment, także wtedy, gdy provider
  dołożył ją wewnątrz strony sięgającej poniżej granicy

#### Scenario: Okno przycięte do granicy konsumenta nic nie przynosi

- **WHEN** ostatnie okno odczytu zostało przycięte do granicy podanej przez konsumenta i provider
  odpowiada na nie brakiem danych albo wyłącznie świecami, które moduł już ma
- **THEN** odczyt kończy się jako osiągnięcie granicy konsumenta
- **AND** odpowiedź MUST NOT stwierdzać, że historia instrumentu się skończyła

#### Scenario: Historia providera kończy się powyżej granicy konsumenta

- **WHEN** provider nie ma nic starszego, a stronicowanie zatrzymało się na oknie, którego starsza
  krawędź wynikała z kalendarza, nie z granicy konsumenta
- **THEN** odpowiedź stwierdza, że historia instrumentu się skończyła — granica konsumenta MUST NOT
  ukryć końca historii, tak samo jak MUST NOT go zmyślić

### Requirement: Głęboki odczyt raportuje swój postęp i koszt

Głęboki odczyt historii może trwać dziesiątki sekund i kosztować dziesiątki żądań do providera.
Moduł MUST podać wraz z wynikiem, ile świec zebrał, ile żądań to kosztowało i jaki okres seria
pokrywa.

#### Scenario: Zakończenie głębokiego odczytu

- **WHEN** głęboki odczyt historii się kończy
- **THEN** odpowiedź podaje liczbę świec, liczbę wysłanych żądań do providera oraz pierwszy
  i ostatni pokryty znacznik czasu

#### Scenario: Wywołujący porzuca głęboki odczyt

- **WHEN** konsument rozłącza się w trakcie głębokiego odczytu
- **THEN** moduł przestaje wysyłać kolejne żądania do providera

### Requirement: Głęboki odczyt zaczyna się w dowolnym momencie, nie tylko teraz

Domyślnie głęboki odczyt sięga wstecz od chwili bieżącej — pierwsze stronicowane żądanie kotwiczy
się na zegarze. Moduł MUST pozwolić wskazać moment, od którego odczyt ma się zacząć, żeby dało się
dociągnąć okno leżące w przeszłości, a nie wyłącznie to, które styka się z teraźniejszością.
Wskazanie takiego momentu MUST NOT zmieniać reguły stronicowania — każde kolejne okno nadal
kotwiczy się na najstarszej już pobranej świecy; zmienia się wyłącznie punkt startowy pierwszego
żądania.

#### Scenario: Odczyt zakotwiczony w przeszłości

- **WHEN** konsument prosi o głęboki odczyt, wskazując moment wcześniejszy niż chwila bieżąca
- **THEN** pierwsze żądanie do providera kończy się na tym momencie, a nie na chwili bieżącej
- **AND** kolejne żądania stronicują wstecz od niego tak samo jak przy odczycie niezakotwiczonym

#### Scenario: Odczyt bez wskazanego momentu

- **WHEN** konsument nie wskazuje momentu, od którego odczyt ma się zacząć
- **THEN** odczyt zaczyna się od chwili bieżącej, jak dotychczas

### Requirement: Odczyt historii mówi, który okres jeszcze trwa

Provider oddaje świece aż do chwili bieżącej, więc najnowsza z nich należy zwykle do okresu,
który się jeszcze nie domknął. Taka świeca ma komplet pól i niczym się nie różni od
zamkniętej, a jej wartości zmienią się jeszcze wielokrotnie. Konsument, który jej nie
odróżni, utrwali cenę w połowie okresu jako wynik całego okresu — i nie dowie się o tym
nigdy, bo dane wyglądają poprawnie.

Moduł MUST przy każdej świecy stwierdzić, czy jej okres się już domknął. Stwierdzenie MUST
wynikać z pomiaru, nie z założenia po stronie konsumenta — moduł jest jedynym miejscem,
które rozmawia z providerem, i jedynym, które może to wiedzieć.

Dla rozdzielczości o stałej długości okresu wystarczy arytmetyka. Dla rozdzielczości,
których granica zależy od sesji rynku, moduł MUST NOT jej wyliczać z zegara — granica
dzienna zgadnięta z północy UTC wygląda poprawnie i jest błędna. Dla nich rozstrzyga stan
rynku instrumentu: dopóki rynek jest otwarty, jego najnowsza świeca należy do okresu, który
trwa.

Odczyt zakotwiczony w przeszłości nie ma świecy w budowie: jego najnowszy okres zamknął się
dawno, niezależnie od tego, co rynek robi teraz.

#### Scenario: Najnowsza świeca odczytu sięgającego teraźniejszości

- **WHEN** konsument prosi o świece do chwili bieżącej w rozdzielczości o stałej długości
  okresu, a okres najnowszej świecy jeszcze się nie skończył
- **THEN** ta świeca jest oznaczona jako należąca do okresu, który trwa
- **AND** każda starsza świeca w tej samej odpowiedzi jest oznaczona jako zamknięta

#### Scenario: Rozdzielczość, której granica zależy od sesji rynku

- **WHEN** konsument prosi o świece do chwili bieżącej w rozdzielczości dziennej albo
  tygodniowej, a rynek instrumentu jest w tej chwili otwarty
- **THEN** najnowsza świeca jest oznaczona jako należąca do okresu, który trwa
- **AND** oznaczenie MUST NOT wynikać z granicy okresu wyliczonej z zegara

#### Scenario: Rynek zamknięty

- **WHEN** konsument prosi o świece w rozdzielczości dziennej albo tygodniowej, a rynek
  instrumentu jest zamknięty
- **THEN** wszystkie zwrócone świece są oznaczone jako zamknięte

#### Scenario: Odczyt zakotwiczony w przeszłości

- **WHEN** konsument prosi o świece kończące się w momencie wcześniejszym niż chwila bieżąca
- **THEN** wszystkie zwrócone świece są oznaczone jako zamknięte

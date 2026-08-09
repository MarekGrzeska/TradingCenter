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


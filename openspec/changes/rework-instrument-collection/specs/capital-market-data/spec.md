## MODIFIED Requirements

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

## ADDED Requirements

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

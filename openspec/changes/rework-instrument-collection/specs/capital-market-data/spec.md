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

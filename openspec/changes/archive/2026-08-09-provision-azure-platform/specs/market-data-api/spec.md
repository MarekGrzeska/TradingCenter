## ADDED Requirements

### Requirement: Katalog instrumentów jest osiągalny przez ten moduł

`capital-gateway` jest niepubliczny — jedynym wywołującym, jaki może mieć skonfigurowane do niego
poświadczenie, jest proces po stronie serwera. Moduł MUST udostępniać wyszukiwanie instrumentów,
listę klas aktywów i katalog instrumentów jako trasy proxujące do gatewaya, tak by `terminal` mógł
osiągnąć te dane bez własnego, bezpośredniego połączenia z gatewayem.

Odpowiedź MUST być tym samym kształtem danych, jaki zwraca gateway — moduł nie interpretuje ani nie
wzbogaca katalogu, wyłącznie go przekazuje.

#### Scenario: Terminal wyszukuje instrument

- **WHEN** konsument prosi ten moduł o wyszukanie instrumentów po frazie
- **THEN** moduł zwraca wynik otrzymany od gatewaya, bez zmiany kształtu

#### Scenario: Terminal pyta o klasy aktywów

- **WHEN** konsument prosi ten moduł o listę klas aktywów
- **THEN** moduł zwraca listę otrzymaną od gatewaya

### Requirement: Odmowa gatewaya jest przezroczysta dla konsumenta

Gdy gateway odmawia lub jest nieosiągalny, moduł MUST NOT udawać pustego wyniku wyszukiwania —
odmowa i brak wyników muszą być rozróżnialne przez wywołującego proxy.

#### Scenario: Gateway odrzuca żądanie proxy

- **WHEN** gateway odrzuca żądanie o katalog instrumentów
- **THEN** moduł zwraca odpowiedź, którą konsument odróżni od pustego wyniku wyszukiwania

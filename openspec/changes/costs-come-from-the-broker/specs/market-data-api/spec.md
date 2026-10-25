## MODIFIED Requirements

### Requirement: Katalog instrumentów jest osiągalny przez ten moduł

`capital-gateway` jest niepubliczny — jedynym wywołującym, jaki może mieć skonfigurowane do niego
poświadczenie, jest proces po stronie serwera. Moduł MUST udostępniać wyszukiwanie instrumentów,
listę klas aktywów, katalog instrumentów **oraz warunki handlowe pojedynczego instrumentu** jako
trasy proxujące do gatewaya, tak by `terminal` i pakiety tego procesu mogły osiągnąć te dane bez
własnego, bezpośredniego połączenia z gatewayem.

Odpowiedź MUST być tym samym kształtem danych, jaki zwraca gateway — moduł nie interpretuje ani nie
wzbogaca katalogu ani warunków, wyłącznie je przekazuje.

#### Scenario: Terminal wyszukuje instrument

- **WHEN** konsument prosi ten moduł o wyszukanie instrumentów po frazie
- **THEN** moduł zwraca wynik otrzymany od gatewaya, bez zmiany kształtu

#### Scenario: Terminal pyta o klasy aktywów

- **WHEN** konsument prosi ten moduł o listę klas aktywów
- **THEN** moduł zwraca listę otrzymaną od gatewaya

#### Scenario: Pakiet pyta o warunki instrumentu

- **WHEN** wołający prosi o warunki handlowe instrumentu
- **THEN** moduł zwraca warunki otrzymane od gatewaya, z finansowaniem overnight, bez zmiany kształtu

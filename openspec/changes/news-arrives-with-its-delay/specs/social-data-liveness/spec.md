## MODIFIED Requirements

### Requirement: Moduł publikuje wiek ostatniego ukończonego przebiegu pętli

Moduł ma dwie pętle. Jedna czyta feed postów i zapisuje to, czego jeszcze nie ma, druga robi to
samo dla feedów newsów. Moduł MUST publikować dla **każdej** z nich osobno, jak dawno ostatnio
**ukończyła** przebieg. MUST mierzyć to w jej własnych interwałach, a nie w sekundach, i MUST
nazywać pętlę, której wartość dotyczy.

Jednostka jest wymaganiem, nie szczegółem. Próbkowanie co minutę i zbieranie co pięć są oba
zdrowe, a jeden próg wyrażony w sekundach byłby zły dla jednego z nich — ta sama decyzja,
którą `market-data-monitoring` podjęło dla wieku świecy. Osobna wartość na pętlę jest wymaganiem
z tego samego powodu: stojąca pętla newsów nie może się schować za chodzącą pętlą postów.

#### Scenario: Pętla chodzi

- **WHEN** pętla kończy przebieg
- **THEN** publikowany wiek wraca do zera i rośnie od nowa

#### Scenario: Pętla stanęła

- **WHEN** od ostatniego ukończonego przebiegu minęło więcej niż kilka interwałów pętli
- **THEN** publikowana wartość rośnie dalej, aż operator ma o czym zostać powiadomiony
- **AND** wartość drugiej pętli, jeśli ta chodzi, MUST NOT tego zasłaniać

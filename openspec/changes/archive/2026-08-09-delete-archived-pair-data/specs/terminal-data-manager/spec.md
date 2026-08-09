## MODIFIED Requirements

### Requirement: Zdjęcie pary jest jawną decyzją

Panel MUST pozwalać skasować pojedynczy interwał instrumentu oraz instrument w całości. Skasowanie
zatrzymuje zbieranie **i** usuwa zebrane dane — panel MUST nazywać tę operację kasowaniem, a nie
zatrzymaniem, bo nazwa jest jedyną rzeczą, którą operator czyta przed kliknięciem.

Obie decyzje MUST wymagać potwierdzenia. Potwierdzenie MUST wymienić, co przestanie być zbierane,
MUST stwierdzić, że zebrane dane zostaną usunięte, i MUST stwierdzić, że jest to nieodwracalne.
Panel MUST NOT zapewniać, że zebrane świece pozostają w archiwum. Panel SHOULD podać przy
potwierdzeniu, od kiedy dane dla tej pary są zebrane, żeby operator widział, ile ich traci.

#### Scenario: Operator zdejmuje parę

- **WHEN** operator wybiera skasowanie jednego interwału instrumentu
- **THEN** panel prosi o potwierdzenie, stwierdzając, że dane tego interwału zostaną usunięte
  nieodwracalnie
- **AND** po potwierdzeniu ten interwał znika z wiersza, a pozostałe zostają

#### Scenario: Operator zdejmuje cały instrument

- **WHEN** operator wybiera skasowanie instrumentu w całości
- **THEN** panel wymienia wszystkie interwały, których dane zostaną usunięte, i prosi o potwierdzenie
- **AND** po potwierdzeniu instrument znika z listy

#### Scenario: Operator wycofuje się z potwierdzenia

- **WHEN** operator odrzuca potwierdzenie
- **THEN** nic nie zostaje skasowane
- **AND** instrument nadal jest archiwizowany

#### Scenario: Kasowanie zawodzi

- **WHEN** archiwum nie wykonuje skasowania
- **THEN** panel mówi, że skasowanie się nie udało, i zostawia możliwość spróbowania raz jeszcze
- **AND** MUST NOT usuwać wiersza z listy, jakby operacja się powiodła

## ADDED Requirements

### Requirement: Skasowanie odsyła do historii

Skasowanie cofa zasięg danych instrumentu i jest jedynym zdarzeniem, które to robi. Po skasowaniu
panel MUST wskazać zakładkę historii jako miejsce, gdzie ten fakt został odnotowany — tak samo jak
dodanie instrumentu wskazuje ją jako miejsce śledzenia dociągania.

#### Scenario: Po skasowaniu

- **WHEN** skasowanie kończy się powodzeniem
- **THEN** panel stwierdza, ile świec zostało usuniętych
- **AND** wskazuje zakładkę historii jako miejsce, gdzie skasowanie jest odnotowane

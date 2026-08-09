## ADDED Requirements

### Requirement: Historia jest ułożona od najnowszego zdarzenia

Zakładka MUST układać wszystkie wpisy jednym porządkiem czasu, od najnowszego do najstarszego,
niezależnie od instrumentu i interwału. Symbol ani interwał MUST NOT być kluczem sortowania —
wiersze pozostają per para, ale to nie one decydują, gdzie wiersz wypadnie.

Zakładka odpowiada przede wszystkim na pytanie „co się właśnie stało", a odpowiedzią na nie jest
zawsze najnowsze zdarzenie. Układ alfabetyczny stawia je w miejscu zależnym od tego, jak nazywa się
instrument, czyli — z punktu widzenia tego pytania — w przypadkowym.

#### Scenario: Zdarzenia różnych par

- **WHEN** operator zlecił dociągnięcie `US100`, a potem skasował dane `GOLD`
- **THEN** wpis o skasowaniu `GOLD` jest wyżej niż wpis o dociągnięciu `US100`
- **AND** kolejność MUST NOT zależeć od tego, jak nazywają się te instrumenty

#### Scenario: Najnowsze zdarzenie jest pierwsze

- **WHEN** operator otwiera zakładkę po zleceniu dociągnięcia
- **THEN** to dociągnięcie jest pierwszym wierszem tabeli
- **AND** operator nie musi go szukać wśród wpisów o innych instrumentach

#### Scenario: Zdarzenia z tego samego momentu

- **WHEN** dwa wpisy niosą ten sam moment
- **THEN** zakładka pokazuje oba, w kolejności stabilnej między odświeżeniami
- **AND** MUST NOT pomijać żadnego ani zmieniać ich miejscami przy kolejnym odczycie

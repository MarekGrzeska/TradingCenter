## ADDED Requirements

### Requirement: Raport niesie krzywą kapitału

Raport MUST zawierać dzienną krzywą kapitału nominalnego, czyli wartość o każdej północy UTC w zakresie, i MUST to być ta
sama seria, z której liczone są Sharpe, Sortino i obsunięcie w procentach. Każdy punkt to wynik zrealizowany i otwarta
pozycja wyceniona na ostatniej minucie przed północą, pomniejszone o narosłe finansowanie. Raport wersji silnika, która
krzywej nie zapisywała, MUST mieć to pole puste.

#### Scenario: Krzywa zgodna z obsunięciem

- **WHEN** z krzywej raportu liczy się największe obsunięcie w procentach
- **THEN** wynik MUST być równy obsunięciu w procentach podanemu w raporcie

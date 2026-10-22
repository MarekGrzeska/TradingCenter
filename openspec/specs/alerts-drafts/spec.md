# alerts-drafts Specification

## Purpose
Reguła opisana zdaniem: model zamienia zdanie operatora na szkic reguły z katalogu, a operator zatwierdza
go jak każdą inną regułę. Model pomaga ją napisać, ale nigdy nie decyduje, że reguła powstaje.

## Requirements

### Requirement: Zdanie może zmieniać istniejącą regułę

Operator MUST móc podać razem ze zdaniem identyfikator istniejącej reguły i dostać szkic tej reguły ze zmianą z
tego zdania, w tej samej strukturze co każdy szkic. Pola, których zdanie nie dotyczy, MUST zostać takie, jakie były,
także te, których model nie wypełnia (bot, sufit na godzinę, włączenie). Szkic zmiany MUST przechodzić tę samą
walidację co zapis i MUST NOT zmieniać żadnej reguły; zużyte tokeny MUST wchodzić w ten sam dobowy sufit. Nieznany
identyfikator MUST być odmową „nie ma takiej reguły”, bez pytania modelu.

#### Scenario: Zmiana progu

- **WHEN** operator pisze „podnieś próg do 1,12” do reguły EURUSD powyżej 1,10 wysyłanej przez wskazanego bota
- **THEN** szkic MUST mieć próg 1,12, a instrument, adresata, bota i czas martwy tej reguły bez zmian
- **AND** reguła w bazie MUST pozostać z progiem 1,10

#### Scenario: Reguła, której nie ma

- **WHEN** operator prosi o zmianę reguły o identyfikatorze, którego nie ma
- **THEN** odpowiedź MUST być odmową, a model MUST NOT zostać zapytany

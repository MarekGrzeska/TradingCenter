## ADDED Requirements

### Requirement: Przebieg da się uruchomić z widoku przebiegów zespołu

Terminal MUST pozwalać uruchomić przebieg zespołu z widoku jego przebiegów, nie tylko
z katalogu. Uruchomienie MUST być potwierdzone przez operatora, a potwierdzenie MUST nazywać
rewizję, która zostanie uruchomiona. Po uruchomieniu widok MUST pokazać nowy przebieg jako
oglądany. Odmowę modułu — wyczerpaną granicę dobową, rewizję nie do uruchomienia —
terminal MUST pokazać słowami modułu.

Widok przebiegów jest miejscem, w którym operator porównuje to, co zespół powiedział wczoraj,
z tym, co mówi dziś. „Uruchom jeszcze raz, teraz" jest tam najczęstszym następnym ruchem,
a droga do niego prowadzi dziś przez wyjście z tego widoku i powrót do niego.

#### Scenario: Uruchomienie z listy przebiegów

- **WHEN** operator potwierdza uruchomienie przebiegu w widoku przebiegów zespołu
- **THEN** rusza przebieg na rewizji nazwanej w potwierdzeniu
- **AND** widok pokazuje ten przebieg jako oglądany

#### Scenario: Uruchomienie odrzucone przez moduł

- **WHEN** moduł odmawia uruchomienia przebiegu
- **THEN** operator widzi powód podany przez moduł
- **AND** oglądany przebieg pozostaje ten, który oglądał

#### Scenario: Rezygnacja z uruchomienia

- **WHEN** operator zamyka potwierdzenie bez zgody
- **THEN** żaden przebieg nie rusza

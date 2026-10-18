## ADDED Requirements

### Requirement: Zakończony przebieg jest zdarzeniem

Moduł MUST ogłosić typ zdarzenia „przebieg zakończony” z atrybutami: zespół, stan końcowy (udany,
nieudany, przerwany, zatrzymany granicą), powód zatrzymania, źródło uruchomienia (operator,
harmonogram, wyzwalacz), koszt przebiegu, informacja, czy przebieg ruszył rachunek, oraz gotowa treść
powiadomienia. Każdy przebieg, który osiągnął stan końcowy, MUST zostać opublikowany z kluczem
źródłowym równym identyfikatorowi przebiegu. Nieudana publikacja MUST NOT zmieniać stanu przebiegu i
MUST być ponawiana, dopóki nie zostanie przyjęta albo nie minie okno ponowień.

#### Scenario: Przebieg z harmonogramu kończy się błędem

- **WHEN** przebieg uruchomiony z harmonogramu kończy się niepowodzeniem
- **THEN** pakiet alertów MUST dostać zdarzenie z tym zespołem, stanem „nieudany” i źródłem „harmonogram”

#### Scenario: Pakiet alertów nieobecny

- **WHEN** przebieg się kończy, a pakiet alertów nie jest zamontowany
- **THEN** przebieg MUST zakończyć się normalnie, bez błędu i bez publikacji

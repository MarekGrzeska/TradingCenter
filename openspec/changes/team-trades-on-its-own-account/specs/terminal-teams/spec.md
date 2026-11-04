## ADDED Requirements

### Requirement: Konto zespołu wybiera się przy granicach handlowych

Terminal MUST pozwalać wybrać konto demo zespołu w tym samym miejscu edytora, w którym
ustawia się granice handlowe. Wybór MUST pochodzić z listy kont, które bramka zna, i MUST
pokazywać nazwę, walutę i saldo każdego konta. Wybór MUST dać się zostawić pusty, a pusty
MUST znaczyć konto aktywne.

Gdy inne zespoły mają przypisane to samo konto, terminal MUST to powiedzieć przy wyborze, ale
MUST NOT blokować zapisu. Dzielone konto miesza wyniki zespołów w jednym saldzie i operator ma
to wiedzieć, zanim zapisze.

Odmowę modułu z powodu narzędzia przełączającego konto albo korygującego saldo w zespole z
kontem terminal MUST pokazać przy agencie, któremu to narzędzie przypisano.

#### Scenario: Operator przypisuje konto

- **WHEN** operator wybiera konto w edytorze zespołu i zapisuje
- **THEN** zapisana rewizja niesie to konto
- **AND** edytor pokazuje je po ponownym otwarciu zespołu

#### Scenario: Konto jest już używane przez inny zespół

- **WHEN** operator wybiera konto przypisane już innemu zespołowi
- **THEN** terminal mówi, który zespół ma to konto
- **AND** zapis pozostaje możliwy

#### Scenario: Moduł odrzuca narzędzie przełączające konto

- **WHEN** moduł odrzuca zapis zespołu z kontem, bo agent ma narzędzie przełączające konto
- **THEN** terminal pokazuje odmowę przy tym agencie

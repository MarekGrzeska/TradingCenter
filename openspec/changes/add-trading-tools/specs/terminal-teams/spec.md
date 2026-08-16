## ADDED Requirements

### Requirement: Złożone zlecenia widać przy agencie, który je złożył

Terminal MUST pokazywać na obrazie przebiegu zlecenia złożone przez zespół — przy tym agencie,
który je złożył — wraz z symbolem, kierunkiem, wielkością i skutkiem. Zlecenie o skutku
nieznanym MUST być pokazane jako nieznane, a MUST NOT być pominięte ani pokazane jako nieudane.

Operator patrzący na przebieg, który rusza rachunek, ma najpierw jedno pytanie: co już poszło.
Odpowiedź schowana w liście wywołań narzędzi jest odpowiedzią, której się szuka.

#### Scenario: Przebieg, w którym padło zlecenie

- **WHEN** agent w trwającym przebiegu składa zlecenie
- **THEN** przy tym agencie pojawia się zlecenie z symbolem, kierunkiem, wielkością i skutkiem

#### Scenario: Zlecenie bez znanego skutku

- **WHEN** wywołanie zapisujące skończyło się awarią dostępu
- **THEN** terminal pokazuje je jako zlecenie o nieznanym skutku

### Requirement: Granice handlowe ustawia się w tym samym widoku co resztę zespołu

Terminal MUST pozwalać ustawić granice handlowe zespołu — maksymalną wielkość zlecenia, liczbę
zleceń na przebieg i dobową — w widoku, w którym operator składa zespół. Odmowa zapisu z powodu
brakującej granicy MUST być pokazana przy agencie, którego dotyczy.

#### Scenario: Operator przypisuje narzędzie zapisujące bez granic

- **WHEN** operator przypisuje agentowi narzędzie zmieniające stan rachunku i zapisuje zespół
  bez ustawionych granic handlowych
- **THEN** terminal pokazuje odmowę przy tym agencie
- **AND** wskazuje brakującą granicę

#### Scenario: Narzędzia zapisujące są rozpoznawalne przy wyborze

- **WHEN** operator wybiera narzędzia dla agenta
- **THEN** narzędzia zmieniające stan rachunku są odróżnione od czytających

### Requirement: Zatrzymanie z powodu granicy zleceń jest pokazane jako takie

Terminal MUST pokazywać granicę zleceń jako przyczynę zatrzymania przebiegu, odróżniając ją od
granicy kosztu, i MUST pokazywać to, co zespół zdążył wypracować i złożyć.

#### Scenario: Przebieg zatrzymany granicą zleceń

- **WHEN** przebieg zostaje zatrzymany po wyczerpaniu dopuszczalnej liczby zleceń
- **THEN** terminal nazywa granicę zleceń jako przyczynę
- **AND** pokazuje złożone dotąd zlecenia

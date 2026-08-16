## ADDED Requirements

### Requirement: Rewizja przypisująca narzędzie zapisujące MUST nieść granice handlowe

Zapis rewizji, w której któremukolwiek agentowi przypisano narzędzie zmieniające stan
rachunku, MUST zostać odrzucony, gdy definicja nie niesie granic handlowych. Odmowa MUST
nazywać agenta i brakującą granicę.

Granice kosztu wolno pominąć — przebieg bez nich najwyżej wyda więcej, niż operator zamierzał,
i widać to na rachunku po fakcie. Zlecenie nie ma tej właściwości, więc jego granica nie jest
polem opcjonalnym w tej samej definicji, w której komuś dano narzędzie do jego złożenia.

#### Scenario: Zapis zespołu z narzędziem zapisującym i bez granic

- **WHEN** operator zapisuje rewizję przypisującą agentowi narzędzie zmieniające stan
  rachunku, bez ustawionych granic handlowych
- **THEN** zapis zostaje odrzucony komunikatem nazywającym agenta i brakującą granicę
- **AND** poprzednia rewizja pozostaje bez zmian

#### Scenario: Zapis zespołu bez narzędzi zapisujących

- **WHEN** operator zapisuje rewizję, której żaden agent nie ma narzędzia zmieniającego stan
  rachunku, i która nie niesie granic handlowych
- **THEN** zapis zostaje przyjęty

#### Scenario: Rewizja z fazy sprzed narzędzi handlowych

- **WHEN** operator odczytuje i uruchamia rewizję zapisaną, zanim granice handlowe istniały
- **THEN** rewizja pozostaje ważna i uruchamialna
- **AND** brak granic handlowych nie jest przy niej odmową

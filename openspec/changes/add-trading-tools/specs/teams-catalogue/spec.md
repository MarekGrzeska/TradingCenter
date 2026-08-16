## ADDED Requirements

### Requirement: Granice handlowe są wyborem operatora, nie warunkiem zapisu

Zapis rewizji MUST NOT zostać odrzucony z powodu pominiętych granic handlowych — także
wtedy, gdy któremuś agentowi przypisano narzędzie zmieniające stan rachunku. Moduł
MUST NOT dopisać do definicji granicy, której operator nie ustawił.

Rozważano regułę odwrotną — „narzędzie zapisujące wymaga granicy" — i została odrzucona.
Zespół handlujący całym kapitałem jest eksperymentem, który operator ma prawo
przeprowadzić, a moduł, który odmawia go zapisać, decyduje za operatora o zakresie jego
własnego doświadczenia. Nieodwracalnemu skutkowi zapobiega tu konto demonstracyjne
wymuszone u gatewaya (`trading-mcp-upstream-access`, "Moduł pracuje wyłącznie na rachunku
demonstracyjnym"), którego żadne ustawienie nie wyłącza — i to jest granica, której nie ma
prawa przesunąć nikt, w odróżnieniu od granic z `teams-trading`, które operator ustawia
sam.

#### Scenario: Zapis zespołu z narzędziem zapisującym i bez granic

- **WHEN** operator zapisuje rewizję przypisującą agentowi narzędzie zmieniające stan
  rachunku, bez ustawionych granic handlowych
- **THEN** zapis zostaje przyjęty
- **AND** rewizja niesie brak granic, a nie granice podstawione przez moduł

#### Scenario: Zapis zespołu bez narzędzi zapisujących

- **WHEN** operator zapisuje rewizję, której żaden agent nie ma narzędzia zmieniającego stan
  rachunku, i która nie niesie granic handlowych
- **THEN** zapis zostaje przyjęty

#### Scenario: Rewizja z fazy sprzed narzędzi handlowych

- **WHEN** operator odczytuje i uruchamia rewizję zapisaną, zanim granice handlowe istniały
- **THEN** rewizja pozostaje ważna i uruchamialna
- **AND** brak granic handlowych nie jest przy niej odmową

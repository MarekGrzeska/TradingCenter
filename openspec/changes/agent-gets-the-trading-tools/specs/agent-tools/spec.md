## RENAMED Requirements

- FROM: `### Requirement: Agent zapisuje wyłącznie w widoku terminala`
- TO: `### Requirement: Agent zapisuje w widoku terminala i na rachunku demonstracyjnym`

## MODIFIED Requirements

### Requirement: Agent zapisuje w widoku terminala i na rachunku demonstracyjnym

Zmianami stanu, jakie moduł MUST umieć wykonać przez narzędzie, są: ustawienie tego, co
terminal rysuje — zestawu wskaźników, symbolu i interwału aktywnego slotu — postawienie i
skasowanie rysunków na wykresie instrumentu (`agent-chart-drawings`) oraz zmiana stanu
rachunku demonstracyjnego: złożenie zlecenia, zamknięcie pozycji, zmiana poziomów
zabezpieczających i anulowanie zlecenia oczekującego.

Moduł MUST NOT wykonywać przez narzędzia żadnej innej zmiany stanu: nie rozpoczyna
zbierania pary, nie kasuje danych, nie zmienia konfiguracji żadnego modułu i nie pisze do
archiwum.

Zapis w widoku terminala MUST być odwracalny ręką operatora, bez rozmowy i bez modelu:
zawartość slotu tym samym wybierakiem, którym operator ustawia wykres sam, a rysunek listą,
z której operator go usuwa. Narzędzie zmieniające widok, którego skutku operator nie umie
cofnąć bez agenta, jest poza tym wymaganiem.

Zapis na rachunku MUST NOT być objęty warunkiem odwracalności, bo objąć się nie da:
zlecenia wykonanego nikt nie cofa wybierakiem, a terminal nie ma dziś ekranu pozycji, więc
jedyną drogą wewnątrz tej platformy jest poprosić agenta jeszcze raz. Na miejscu
odwracalności stoją trzy rzeczy i żadna z nich nie jest liczbą wpisaną w ten moduł:
rachunek demonstracyjny wymuszony u gatewaya (`capital-trading`, „Handel dotyka wyłącznie
konta demo"), imienna lista wołających u serwera narzędzi zapisujących
(`trading-mcp-transport`) oraz ślad każdego wywołania ruszającego rachunek
(`agent-trading`).

#### Scenario: Operator prosi o pokazanie wskaźnika

- **WHEN** operator prosi agenta, żeby pokazał EMA 200 na wykresie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o naniesienie oporu

- **WHEN** operator prosi agenta, żeby naniósł opór na wskazanej cenie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o złożenie zlecenia

- **WHEN** operator prosi agenta, żeby złożył zlecenie na wskazanym instrumencie
- **THEN** agent ma narzędzie, którym to robi, i zlecenie zostaje złożone na rachunku
  demonstracyjnym
- **AND** MUST NOT odpowiedzieć, że jest to poza jego zakresem

#### Scenario: Operator prosi o wykonanie akcji poza tymi dwoma zakresami

- **WHEN** operator prosi agenta, żeby zaczął zbierać parę albo skasował dane z archiwum
- **THEN** agent nie ma narzędzia, którym mógłby to zrobić
- **AND** odpowiada, że to jest poza jego zakresem, zamiast zgłaszać chwilową awarię

#### Scenario: Operator cofa to, co ustawił agent

- **WHEN** operator usuwa wybierakiem wskaźnik, który ustawił agent
- **THEN** wskaźnik znika i nie wraca sam z siebie

#### Scenario: Operator cofa to, co narysował agent

- **WHEN** operator usuwa z listy rysunek, który postawił agent
- **THEN** rysunek znika i nie wraca sam z siebie

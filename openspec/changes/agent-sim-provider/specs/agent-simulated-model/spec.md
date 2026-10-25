## Purpose

Opisuje model zastępczy rozmowy: dostawcę, który zamiast wołać OpenAI odtwarza scenariusz z pliku, żeby testy na
lokalnym stosie przechodziły przez prawdziwą turę, narzędzia i terminal bez kosztu i bez sieci.

## ADDED Requirements

### Requirement: Symulacja jest wyborem, odmawianym poza trybem lokalnym

Workbench MUST wybierać dostawcę modelu rozmowy ustawieniem `AGENT_PROVIDER`: `openai` (domyślnie) albo `sim`. Inna
wartość MUST być odmową startu z nazwą dopuszczalnych. Przy `sim` ustawienie `AGENT_SIM_SCENARIO` MUST wskazywać plik
scenariusza; jego brak MUST być odmową startu. Gdy ustawiono `DATABASE_USER`, `sim` MUST być odmową startu, bo to
wdrożenie.

#### Scenario: Symulacja na wdrożeniu

- **WHEN** workbench startuje z `AGENT_PROVIDER=sim` i ustawionym `DATABASE_USER`
- **THEN** start MUST się nie udać, a komunikat MUST nazywać oba ustawienia

#### Scenario: Domyślny dostawca

- **WHEN** `AGENT_PROVIDER` nie jest ustawione
- **THEN** rozmowa MUST wołać OpenAI jak dotąd

### Requirement: Scenariusz odtwarza wywołania modelu

Scenariusz MUST składać się z reguł sprawdzanych po kolei; pierwsza, której wyrażenie regularne pasuje do całej ostatniej
wiadomości operatora, MUST decydować o turze. Reguła MUST opisywać kolejne wywołania modelu w turze: każde jest albo
listą próśb o narzędzia z argumentami, albo tekstem, a ostatnie MUST być tekstem. Nazwane grupy wyrażenia MUST być
podstawiane w argumentach w miejscu `{nazwa}`, a wartość składająca się z samych cyfr MUST trafić do narzędzia jako
liczba. Wiadomość bez pasującej reguły MUST dostać odpowiedź mówiącą, że scenariusz jej nie zna, a MUST NOT kończyć tury
błędem. Plik, którego nie da się odczytać albo który łamie te zasady, MUST być odmową startu.

#### Scenario: Szkic dla strategii z wiadomości

- **WHEN** reguła `^E2E szkic (?<id>\d+)$` prosi o `draft_strategy` z argumentem `strategy_id` równym `{id}`, a operator
  pisze „E2E szkic 7”
- **THEN** narzędzie MUST dostać `strategy_id` równe liczbie 7, a po jego wyniku tura MUST zakończyć się tekstem reguły

#### Scenario: Wiadomość spoza scenariusza

- **WHEN** żadna reguła nie pasuje do wiadomości operatora
- **THEN** agent MUST odpowiedzieć tekstem mówiącym, że scenariusz nie zna tej wiadomości

### Requirement: Symulacja nie wychodzi poza proces

Dostawca symulowany MUST NOT otwierać połączenia sieciowego. Prośby o narzędzia MUST wykonywać się tymi samymi
narzędziami co przy OpenAI, z ich zapisem w transkrypcie. Każde wywołanie MUST zostawić wiersz zużycia z zerem tokenów
wejścia i wyjścia, odróżnialny od zużycia nieznanego.

#### Scenario: Narzędzie w symulowanej turze

- **WHEN** scenariusz prosi o `draft_strategy` z poprawnym dokumentem
- **THEN** szkic MUST zostać zapisany w bazie strategii tak samo jak w turze z OpenAI

#### Scenario: Zużycie symulowanej tury

- **WHEN** symulowana tura woła model dwa razy
- **THEN** MUST powstać dwa wiersze zużycia z zerem tokenów wejścia i wyjścia

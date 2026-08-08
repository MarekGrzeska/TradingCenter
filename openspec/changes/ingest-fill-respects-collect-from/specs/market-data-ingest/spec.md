## MODIFIED Requirements

### Requirement: Uzupełnianie wstecz sięga po historię

Moduł MUST umieć dociągnąć świece starsze niż moment rozpoczęcia śledzenia, korzystając z odczytu
historii `capital-gateway`. MUST NOT stronicować sam — gateway robi to za limitem tysiąca świec na
żądanie i ta logika MUST NOT być powielana.

Głębokość, do której to cichy fill sięga dla pary bez żadnej świecy, MUST NOT przekraczać momentu
`collect_from` tej pary — momentu, od którego historia ma być pokryta, wskazanego przez operatora
albo wyliczonego z domyślnej głębokości, gdy operator nic nie wskazał (`market-data-tracking`
spec, „Para niesie moment, od którego ma być pokryta"). Dla pary bez jawnie wskazanego momentu
`collect_from` i skonfigurowana domyślna głębokość mówią to samo, więc dla niej nic się nie
zmienia; dla pary z jawnym, płytszym momentem fill MUST zatrzymać się na nim, a nie sięgać dalej
tylko dlatego, że skonfigurowana głębokość jest większa.

#### Scenario: Nowo dodana para

- **WHEN** operator zaczyna śledzić parę, dla której archiwum nie ma nic, bez wskazania momentu,
  od którego chce historii
- **THEN** moduł dociąga historię wstecz do skonfigurowanej domyślnej głębokości
- **AND** zapisuje zakres, który udało się pokryć

#### Scenario: Nowo dodana para z jawną, płytszą datą OD

- **WHEN** operator zaczyna śledzić parę, wskazując moment, od którego chce historii, płytszy niż
  skonfigurowana domyślna głębokość
- **THEN** cichy fill dociąga historię wstecz najwyżej do tego momentu
- **AND** MUST NOT zapisać ani jednej świecy starszej niż on

#### Scenario: Provider nie ma starszych danych

- **WHEN** uzupełnianie dochodzi do końca historii dostępnej u providera, zanim osiągnie
  `collect_from`
- **THEN** moduł zatrzymuje się, co nie jest błędem
- **AND** zapisuje ten punkt jako najstarszą granicę pokrycia

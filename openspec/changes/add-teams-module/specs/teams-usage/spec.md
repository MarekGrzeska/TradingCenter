## Purpose

Ile kosztuje praca zespołu: co moduł mierzy przy każdym wywołaniu modelu, jak zapisuje koszt,
żeby zgadzał się z fakturą, i gdzie przebiegają granice, po przekroczeniu których przebieg
zostaje zatrzymany.

## ADDED Requirements

### Requirement: Każde wywołanie modelu zostawia własny wiersz zużycia

Moduł MUST zapisać osobny wiersz zużycia dla każdego wywołania modelu, wraz ze wskazaniem
przebiegu, agenta i modelu, którego dotyczy. Przebieg, w którym pracowało N agentów po kilka
rund każdy, MUST zostawić po jednym wierszu na każde wywołanie, a MUST NOT jeden wiersz na
przebieg ani jeden na agenta.

Sumowanie po przebiegu jest wtedy dodawaniem, a rozbicie kosztu na role — pytaniem, na które
dane już odpowiadają. Zsumowane przy zapisie nie dałyby się rozdzielić później, a to właśnie
rozkład kosztu między rolami jest jedną z rzeczy, które ten moduł ma zmierzyć.

#### Scenario: Przebieg z kilkoma agentami

- **WHEN** kończy się przebieg, w którym trzej agenci byli wołani po dwa razy
- **THEN** powstaje sześć wierszy zużycia
- **AND** każdy wskazuje swojego agenta i model

#### Scenario: Odczyt zużycia w rozbiciu na role

- **WHEN** wołający pyta o zużycie zakończonego przebiegu
- **THEN** dostaje je w rozbiciu pozwalającym przypisać koszt poszczególnym agentom

### Requirement: Koszt jest przypisany do wiersza w chwili zapisu

Stawka za tokeny MUST być konfiguracją, nie stałą w kodzie. Koszt wiersza zużycia MUST być
policzony i zapisany w chwili powstania wiersza, wraz ze stawkami, których użyto, i MUST NOT
być przeliczany przy odczycie.

Cennik zmieniany po fakcie przesunąłby koszt każdego wcześniejszego przebiegu i rozjechał sumy
z fakturą — a zgodność z fakturą jest jedynym powodem, dla którego ten pomiar istnieje.

#### Scenario: Cennik zmienia się po przebiegu

- **WHEN** stawka modelu zostaje zmieniona, a operator otwiera zużycie przebiegu sprzed zmiany
- **THEN** koszt tamtych wierszy jest taki jak w chwili ich zapisu
- **AND** wiersze powstałe po zmianie niosą stawkę nową

#### Scenario: Model nie zwrócił liczby tokenów

- **WHEN** wywołanie modelu kończy się bez informacji o zużyciu tokenów
- **THEN** wiersz zużycia odnotowuje brak tej informacji
- **AND** MUST NOT zapisywać go jako zużycia zerowego

### Requirement: Przekroczenie granicy kosztu zatrzymuje przebieg

Definicja zespołu MUST móc nieść granicę kosztu jednego przebiegu oraz granicę kosztu dobowego
dla zespołu. Moduł MUST sprawdzić granicę przed wywołaniem modelu i MUST zatrzymać przebieg ze
statusem nazywającym koszt jako przyczynę, zamiast wykonać wywołanie przekraczające granicę.

Sprawdzenie MUST zapadać w module, a MUST NOT być powierzone treści promptu. Prompt jest
proszeniem modelu, żeby się ograniczył; granica kosztu ma trzymać także wtedy, gdy model
poprosi o to, o co nie powinien — a przy zespole wołanym harmonogramem w nocy jest to jedyna
rzecz stojąca między eksperymentem a rachunkiem, którego nikt nie zatwierdził.

#### Scenario: Przebieg dobija do granicy w połowie pracy

- **WHEN** koszt trwającego przebiegu osiąga granicę przed wywołaniem kolejnego agenta
- **THEN** przebieg zostaje zatrzymany ze statusem nazywającym koszt jako przyczynę
- **AND** ślad tego, co zdążyło się wydarzyć, pozostaje zapisany

#### Scenario: Zespół wyczerpał granicę dobową

- **WHEN** operator uruchamia przebieg zespołu, którego koszt dobowy jest już wyczerpany
- **THEN** moduł odmawia uruchomienia, nazywając granicę dobową jako przyczynę

#### Scenario: Zespół bez ustawionych granic

- **WHEN** definicja nie niesie żadnej granicy kosztu
- **THEN** przebieg rusza i nie jest zatrzymywany z powodu kosztu

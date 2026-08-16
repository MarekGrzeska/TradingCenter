## MODIFIED Requirements

### Requirement: Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie

Moduł MAY być skonfigurowany z więcej niż jednym serwerem narzędzi. Dla **każdego** z nich
konfiguracja MUST wskazywać dokładnie jeden tryb dostępu: tożsamość wobec adresu zdalnego albo
pętlę zwrotną bez niej. Konfiguracja nazywająca oba tryby naraz dla któregokolwiek serwera
MUST być odrzucona przy starcie, zanim moduł zacznie odpowiadać na cokolwiek. Adres inny niż
pętla zwrotna bez skonfigurowanej tożsamości MUST być odmową startu.

Serwer nieskonfigurowany pozostaje stanem wspieranym — osobno dla każdego z nich. Moduł bez
serwera zapisu obsługuje katalog i uruchamia zespoły, którym zapis nie jest przypisany.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem serwera narzędzi spoza pętli zwrotnej i bez
  skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i adres w pętli zwrotnej
- **THEN** moduł MUST odmówić startu, zamiast wybrać jeden z nich

#### Scenario: Niespójność dotyczy drugiego serwera

- **WHEN** konfiguracja jednego serwera narzędzi jest spójna, a drugiego nie
- **THEN** moduł MUST odmówić startu z komunikatem nazywającym ten serwer, którego
  konfiguracja jest niespójna

#### Scenario: Skonfigurowany jeden serwer z dwóch

- **WHEN** moduł startuje ze skonfigurowanym serwerem odczytu i bez serwera zapisu
- **THEN** wstaje i obsługuje katalog
- **AND** uruchamia przebiegi zespołów, których agenci nie mają narzędzi zapisujących

### Requirement: Brak serwera narzędzi zatrzymuje przebieg, zamiast pozwolić zespołowi zgadywać

Jeżeli którykolwiek agent w definicji ma przypisane narzędzia, a serwer, który je ogłasza,
jest nieskonfigurowany, nieosiągalny albo odmawia tożsamości, moduł MUST odmówić uruchomienia
przebiegu i MUST nazwać dostęp do narzędzi jako przyczynę, wskazując ten serwer. Moduł MUST
wstać i obsługiwać katalog także wtedy, gdy któregokolwiek serwera narzędzi nie ma — odmowa
dotyczy uruchomienia przebiegu, nie startu modułu.

Tu przebiega różnica wobec rozmowy operatora z modelem, gdzie tura bez narzędzi jest gorszą,
ale użyteczną odpowiedzią (`agent-tool-access`, „Brak serwera narzędzi nie odbiera agentowi
mowy"). Zespół pozbawiony danych nie odpowiada gorzej — produkuje kilku agentów zgadujących
niezależnie od siebie, płatnych za każde zgadnięcie, i ślad, który wygląda jak wynik
eksperymentu, a nim nie jest. Przy serwerze zapisu jest gorzej jeszcze o jedno: zespół, który
uważa, że złożył zlecenie, a nie złożył, produkuje wniosek o rachunku, którego nie ruszył.

#### Scenario: Serwer narzędzi nieosiągalny przy uruchomieniu

- **WHEN** operator uruchamia przebieg zespołu, którego agenci mają przypisane narzędzia,
  a serwer narzędzi nie odpowiada
- **THEN** moduł odmawia uruchomienia, nazywając dostęp do narzędzi jako przyczynę
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Zespół, w którym nikt nie ma narzędzi

- **WHEN** operator uruchamia przebieg zespołu, którego żaden agent nie ma przypisanych
  narzędzi, a serwer narzędzi jest nieosiągalny
- **THEN** przebieg rusza normalnie

#### Scenario: Moduł startuje bez serwera narzędzi

- **WHEN** moduł startuje, a serwer narzędzi jest nieskonfigurowany
- **THEN** moduł wstaje i obsługuje katalog zespołów

#### Scenario: Nieosiągalny jest tylko serwer, z którego nikt nic nie ma

- **WHEN** operator uruchamia przebieg zespołu, którego agenci mają wyłącznie narzędzia
  odczytu, a nieosiągalny jest serwer zapisu
- **THEN** przebieg rusza normalnie
- **AND** nieosiągalny serwer nie jest w ogóle pytany

## ADDED Requirements

### Requirement: Ta sama nazwa narzędzia z dwóch serwerów jest odmową

Gdy dwa skonfigurowane serwery ogłaszają narzędzie o tej samej nazwie, moduł MUST odmówić —
przy zapisie rewizji przypisującej tę nazwę i przy uruchomieniu przebiegu, który ją niesie —
komunikatem nazywającym oba serwery. Moduł MUST NOT wybrać jednego z nich.

Definicja wskazuje narzędzie po nazwie i tylko po nazwie (patrz „Moduł nie trzyma kopii tego,
co ogłasza serwer narzędzi"), więc przy kolizji nie ma czym rozstrzygnąć, które z dwóch miał
na myśli operator. Cichy wybór jednego z nich dałby przebiegi, które różnią się użytym
narzędziem, a wyglądają identycznie w rewizji.

#### Scenario: Dwa serwery ogłaszają tę samą nazwę

- **WHEN** operator uruchamia przebieg, którego agent ma przypisane narzędzie o nazwie
  ogłaszanej przez oba serwery
- **THEN** moduł odmawia uruchomienia, nazywając nazwę i oba serwery
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Kolizja przy zapisie rewizji

- **WHEN** operator zapisuje rewizję przypisującą agentowi nazwę ogłaszaną przez oba serwery
- **THEN** zapis zostaje odrzucony komunikatem nazywającym nazwę i oba serwery

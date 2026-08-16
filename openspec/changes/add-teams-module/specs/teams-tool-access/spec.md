## Purpose

Warunki, na jakich moduł łączy się z serwerem narzędzi: czym się przed nim przedstawia, jak
narzędzia trafiają do poszczególnych agentów, co się dzieje, gdy serwera nie ma, i dlaczego
moduł nie trzyma u siebie kopii tego, co tamten publikuje.

## ADDED Requirements

### Requirement: Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie

Konfiguracja MUST wskazywać dokładnie jeden tryb dostępu do serwera narzędzi: tożsamość wobec
adresu zdalnego albo pętlę zwrotną bez niej. Konfiguracja nazywająca oba tryby naraz MUST być
odrzucona przy starcie, zanim moduł zacznie odpowiadać na cokolwiek. Adres inny niż pętla
zwrotna bez skonfigurowanej tożsamości MUST być odmową startu.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem serwera narzędzi spoza pętli zwrotnej i bez
  skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i adres w pętli zwrotnej
- **THEN** moduł MUST odmówić startu, zamiast wybrać jeden z nich

### Requirement: Agent dostaje narzędzia wskazane w definicji, a nie wszystkie

Model wołany w imieniu agenta MUST dostać wyłącznie te narzędzia, które definicja przypisała
temu agentowi. Narzędzie ogłaszane przez serwer, a nieprzypisane agentowi, MUST NOT trafić do
jego wywołania.

Podział narzędzi jest częścią eksperymentu, nie jego oprawą: rola, która ma czytać wykres, i
rola, która ma ważyć argumenty, różnią się między innymi tym, po co wolno im sięgnąć. Zespół,
w którym każdy dostaje wszystko, nie sprawdza tego podziału.

#### Scenario: Rola z zawężonym zestawem

- **WHEN** definicja przypisuje agentowi dwa narzędzia spośród ogłaszanych przez serwer
- **THEN** model wołany w jego imieniu dostaje dokładnie te dwa
- **AND** pozostałe nie są mu podane

#### Scenario: Narzędzie znika po stronie serwera

- **WHEN** serwer przestaje ogłaszać narzędzie przypisane agentowi w zapisanej rewizji
- **THEN** uruchomienie tej rewizji MUST zostać odrzucone z komunikatem nazywającym narzędzie
- **AND** rewizja pozostaje czytelna

### Requirement: Brak serwera narzędzi zatrzymuje przebieg, zamiast pozwolić zespołowi zgadywać

Jeżeli którykolwiek agent w definicji ma przypisane narzędzia, a serwer narzędzi jest
nieskonfigurowany, nieosiągalny albo odmawia tożsamości, moduł MUST odmówić uruchomienia
przebiegu i MUST nazwać dostęp do narzędzi jako przyczynę. Moduł MUST wstać i obsługiwać
katalog także wtedy, gdy serwera narzędzi nie ma — odmowa dotyczy uruchomienia przebiegu, nie
startu modułu.

Tu przebiega różnica wobec rozmowy operatora z modelem, gdzie tura bez narzędzi jest gorszą,
ale użyteczną odpowiedzią (`agent-tool-access`, „Brak serwera narzędzi nie odbiera agentowi
mowy"). Zespół pozbawiony danych nie odpowiada gorzej — produkuje kilku agentów zgadujących
niezależnie od siebie, płatnych za każde zgadnięcie, i ślad, który wygląda jak wynik
eksperymentu, a nim nie jest.

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

### Requirement: Wołanie serwera narzędzi ma skończony czas

Każde wywołanie narzędzia MUST mieć górną granicę czasu oczekiwania. Po jej przekroczeniu moduł
MUST oddać modelowi wynik nazywający awarię dostępu. Przekroczenie czasu MUST być odróżnialne
od odmowy narzędzia: jedno mówi „nie udało się zapytać", drugie „zapytano i odpowiedziano, że
tak nie można".

#### Scenario: Narzędzie nie odpowiada w czasie

- **WHEN** wywołanie narzędzia przekracza dozwolony czas
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** ślad przebiegu odróżnia to od odmowy narzędzia

### Requirement: Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi

Moduł MUST NOT importować kodu serwera narzędzi ani żadnego innego modułu. Nazwy narzędzi, ich
opisy i kształty parametrów MUST pochodzić z sesji z serwerem, a nie z pliku w tym module.
Definicja zespołu wskazuje narzędzia po nazwie i MUST NOT nieść ich opisu ani kształtu
parametrów.

Kontrakt jedzie tu w tej samej sesji, w której jest używany, więc nie ma dwóch kopii do
rozjechania i MUST NOT powstać trzecia — ani w postaci wpisanej na stałe listy, ani w postaci
opisu zamrożonego w zapisanej rewizji.

#### Scenario: Opis narzędzia zmienia się po stronie serwera

- **WHEN** serwer zmienia opis narzędzia przypisanego agentowi w zapisanej rewizji
- **THEN** model dostaje opis nowy
- **AND** rewizja nie wymaga przepisania

## ADDED Requirements

### Requirement: Narzędzie w tym samym procesie jest źródłem, ale nie serwerem

Moduł MAY ogłaszać agentom narzędzia pochodzące z **niego samego**, obok narzędzi ogłaszanych przez
serwery narzędzi. Takie źródło MUST podlegać każdej regule tej specyfikacji, która mówi o doborze
narzędzi i o ich wołaniu — przypisanie w definicji, odmowa przy nazwie nieprzypisanej, kolizja nazw
z innym źródłem, skończony czas wywołania — i MUST NOT podlegać regułom, które opisują drogę przez
sieć: nie ma adresu, nie przedstawia tożsamości, nie bywa nieskonfigurowane i nie traci sesji.

Źródło w procesie MUST być zawsze dostępne, dopóki moduł odpowiada. Przebieg, którego agenci mają
przypisane wyłącznie narzędzia takiego źródła, MUST ruszyć także wtedy, gdy żaden serwer narzędzi
nie jest skonfigurowany ani osiągalny.

Rozróżnienie jest tu potrzebne, bo pytania „czym się przedstawiasz" i „co robimy, gdy nie
odpowiadasz" nie mają sensu wobec funkcji w tym samym procesie, a odpowiedź „nie dotyczy" wpisana
milcząco byłaby nieodróżnialna od przeoczenia. Reguły doboru natomiast obowiązują bez wyjątku:
agent, który nie dostał narzędzia w definicji, nie dostaje go i tutaj.

#### Scenario: Zespół sięgający wyłącznie po narzędzia z procesu

- **WHEN** operator uruchamia przebieg zespołu, którego agenci mają przypisane wyłącznie narzędzia
  źródła w procesie, a żaden serwer narzędzi nie jest skonfigurowany
- **THEN** przebieg rusza normalnie

#### Scenario: Nazwa z procesu zderza się z nazwą z serwera

- **WHEN** serwer narzędzi zaczyna ogłaszać nazwę, którą ogłasza już źródło w procesie, a operator
  uruchamia przebieg przypisujący tę nazwę
- **THEN** moduł odmawia uruchomienia, nazywając nazwę i oba źródła
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Zapis rewizji z narzędziem z procesu

- **WHEN** operator zapisuje rewizję przypisującą agentowi narzędzie ogłaszane przez źródło
  w procesie, a serwery narzędzi są nieosiągalne
- **THEN** zapis zostaje przyjęty, bo nazwa jest potwierdzona przez źródło, które odpowiedziało

## MODIFIED Requirements

### Requirement: Agent dostaje narzędzia wskazane w definicji, a nie wszystkie

Model wołany w imieniu agenta MUST dostać wyłącznie te narzędzia, które definicja przypisała
temu agentowi. Narzędzie ogłaszane przez serwer, a nieprzypisane agentowi, MUST NOT trafić do
jego wywołania.

Przypisanie MUST obowiązywać także **przy wywołaniu**, nie tylko przy doborze. Wywołanie narzędzia
o nazwie nieprzypisanej temu agentowi MUST zostać odrzucone wynikiem nazywającym brak przypisania,
i MUST NOT zostać wykonane u żadnego źródła. Odmowa MUST zostać w śladzie przebiegu jak każde inne
wywołanie.

Dobór jest ochroną przed pomyłką, nie przed próbą. Model pisze nazwę narzędzia sam i nic nie
powstrzymuje go przed napisaniem nazwy, której nie dostał — z opisu innego narzędzia, z briefingu
poprzednika albo po prostu z rozpędu. Dopóki wszystkie ogłaszane narzędzia tylko czytały, różnica
była teoretyczna; przy narzędziach dzielących agentów na piszących i czytających jest to cała
przypisana granica.

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

#### Scenario: Model woła nazwę, której nie dostał

- **WHEN** model wołany w imieniu agenta prosi o narzędzie ogłaszane przez którekolwiek źródło, ale
  nieprzypisane temu agentowi w definicji
- **THEN** wywołanie MUST zostać odrzucone wynikiem nazywającym brak przypisania
- **AND** MUST NOT zostać wykonane u źródła, które tę nazwę ogłasza

#### Scenario: Model woła nazwę, której nikt nie ogłasza

- **WHEN** model wołany w imieniu agenta prosi o narzędzie, którego nie ogłasza żadne źródło
- **THEN** dostaje wynik nazywający nieznane narzędzie
- **AND** przebieg pracuje dalej

### Requirement: Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi

Moduł MUST NOT importować kodu serwera narzędzi ani żadnego innego modułu. Nazwy narzędzi, ich
opisy i kształty parametrów ogłaszane przez **serwer** MUST pochodzić z sesji z tym serwerem, a nie
z pliku w tym module. Definicja zespołu wskazuje narzędzia po nazwie i MUST NOT nieść ich opisu ani
kształtu parametrów — niezależnie od tego, które źródło je ogłasza.

Kontrakt jedzie tu w tej samej sesji, w której jest używany, więc nie ma dwóch kopii do
rozjechania i MUST NOT powstać trzecia — ani w postaci wpisanej na stałe listy, ani w postaci
opisu zamrożonego w zapisanej rewizji.

Narzędzie ogłaszane przez sam moduł jest wyjątkiem od pierwszego zdania i nie jest wyjątkiem od
drugiego: jego opis stoi w pliku tego modułu, bo nie ma innego miejsca, w którym mógłby stać, i nie
jest kopią niczego. Zakaz dotyczy trzymania u siebie **cudzego** kontraktu, a nie posiadania
własnego.

#### Scenario: Opis narzędzia zmienia się po stronie serwera

- **WHEN** serwer zmienia opis narzędzia przypisanego agentowi w zapisanej rewizji
- **THEN** model dostaje opis nowy
- **AND** rewizja nie wymaga przepisania

#### Scenario: Rewizja z narzędziem modułu

- **WHEN** operator zapisuje rewizję przypisującą agentowi narzędzie ogłaszane przez sam moduł
- **THEN** rewizja niesie samą nazwę
- **AND** MUST NOT nieść opisu ani kształtu parametrów tego narzędzia

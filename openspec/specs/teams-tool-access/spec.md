# teams-tool-access Specification

## Purpose
Warunki, na jakich moduł łączy się z serwerem narzędzi: czym się przed nim przedstawia, jak
narzędzia trafiają do poszczególnych agentów, co się dzieje, gdy serwera nie ma, i dlaczego
moduł nie trzyma u siebie kopii tego, co tamten publikuje.
## Requirements
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
- **AND** nieosiągalność serwera zapisu nie wpływa na wynik — żadna nazwa przypisana w
  definicji nie zostaje bez wyjaśnienia po stronie serwerów, które odpowiedziały

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

### Requirement: Ta sama nazwa narzędzia z dwóch serwerów jest odmową

Gdy więcej niż jeden skonfigurowany serwer ogłasza narzędzie o tej samej nazwie, moduł MUST
odmówić — przy zapisie rewizji przypisującej tę nazwę i przy uruchomieniu przebiegu, który ją
niesie — komunikatem nazywającym **wszystkie** serwery, które tę nazwę ogłaszają. Moduł MUST NOT
wybrać jednego z nich i MUST NOT wymienić tylko dwóch pierwszych: komunikat, który nie wymienia
wszystkich, każe operatorowi odkonfigurować serwer i zobaczyć tę samą odmowę jeszcze raz.

Definicja wskazuje narzędzie po nazwie i tylko po nazwie (patrz „Moduł nie trzyma kopii tego,
co ogłasza serwer narzędzi"), więc przy kolizji nie ma czym rozstrzygnąć, który z nich miał na
myśli operator. Cichy wybór jednego z nich dałby przebiegi, które różnią się użytym narzędziem,
a wyglądają identycznie w rewizji.

Liczba serwerów jest konfiguracją, nie stałą: moduł MAY być skonfigurowany z dowolną ich liczbą
(patrz „Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie"), a wymaganie to MUST NOT
zakładać żadnej konkretnej.

#### Scenario: Dwa serwery ogłaszają tę samą nazwę

- **WHEN** operator uruchamia przebieg, którego agent ma przypisane narzędzie o nazwie ogłaszanej
  przez dwa skonfigurowane serwery
- **THEN** moduł odmawia uruchomienia, nazywając nazwę i oba serwery
- **AND** żaden agent nie zostaje wywołany

#### Scenario: Kolizja przy zapisie rewizji

- **WHEN** operator zapisuje rewizję przypisującą agentowi nazwę ogłaszaną przez więcej niż jeden
  serwer
- **THEN** zapis zostaje odrzucony komunikatem nazywającym nazwę i wszystkie te serwery

#### Scenario: Kolizja obejmuje więcej niż dwa serwery

- **WHEN** tę samą nazwę narzędzia ogłaszają trzy skonfigurowane serwery
- **THEN** komunikat odmowy wymienia wszystkie trzy
- **AND** MUST NOT wymieniać wyłącznie dwóch z nich

### Requirement: Wywołanie odrzucone z powodu nieznanej sesji jest ponawiane raz

Moduł utrzymuje sesję z serwerem narzędzi między wywołaniami, a serwer może ją stracić bez
uprzedzenia — restart serwera jest tego zwykłym powodem. Kiedy serwer odrzuca wywołanie,
stwierdzając, że sesji nie zna, moduł MUST odtworzyć sesję i wysłać to samo wywołanie
**dokładnie raz** jeszcze. Drugie niepowodzenie MUST być oddane modelowi jako awaria dostępu,
bez trzeciej próby.

Ponowienie MUST być ograniczone do odpowiedzi, która **dowodzi, że żądanie nie zostało
obsłużone**. Przekroczony czas oczekiwania, awaria po stronie serwera i zerwane połączenie
MUST NOT być ponawiane: po żadnym z nich nie wiadomo, czy żądanie dotarło, a wywołanie
zmieniające rachunek powtórzone po takim stanie jest drugim zleceniem, nie ponowieniem
pierwszego. To rozróżnienie MUST być przeprowadzone na tym, co odpowiedział serwer, a nie na
nazwie wywoływanego narzędzia — narzędzie czytające i zapisujące odrzucone przy tej samej
bramce są odrzucone tak samo.

Ponowienie MUST zostawić w śladzie przebiegu **jeden** wpis wywołania. Model wywołał
narzędzie raz i ponowienie nie jest jego decyzją; ślad pokazujący dwa wpisy kazałby czytać
jako dwie próby coś, co próbą było raz.

#### Scenario: Serwer narzędzi wstał od nowa między wywołaniami

- **WHEN** serwer odrzuca wywołanie, nie znając sesji, którą moduł trzymał
- **THEN** moduł otwiera sesję na nowo i wysyła to samo wywołanie jeszcze raz
- **AND** model dostaje wynik tego wywołania, a nie awarię dostępu

#### Scenario: Sesji nie da się odtworzyć

- **WHEN** wywołanie zostaje odrzucone z powodu nieznanej sesji, a ponowienie po jej
  odtworzeniu również się nie udaje
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** żadna trzecia próba nie jest podejmowana

#### Scenario: Wywołanie przekracza dozwolony czas

- **WHEN** wywołanie narzędzia nie kończy się odpowiedzią w dozwolonym czasie
- **THEN** moduł MUST NOT wysłać go ponownie
- **AND** model dostaje wynik nazywający awarię dostępu i nieznany skutek wywołania

#### Scenario: Ślad ponowionego wywołania

- **WHEN** wywołanie udaje się dopiero po odtworzeniu sesji
- **THEN** ślad przebiegu niesie jeden wpis tego wywołania, z jego wynikiem

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


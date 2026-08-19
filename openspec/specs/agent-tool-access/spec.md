# agent-tool-access Specification

## Purpose

Warunki, na jakich moduł łączy się z serwerem narzędzi: czym się przed nim przedstawia,
jak długo czeka, co robi, gdy serwera nie ma, i dlaczego nie trzyma u siebie kopii tego,
co tamten publikuje.
## Requirements
### Requirement: Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie

Konfiguracja MUST wskazywać dla **każdego** serwera narzędzi osobno dokładnie jeden tryb
dostępu: tożsamość wobec adresu zdalnego albo pętla zwrotna bez niej. Konfiguracja nazywająca
oba tryby naraz dla tego samego serwera MUST być odrzucona przy starcie, zanim moduł zacznie
odpowiadać na cokolwiek.

Adres inny niż pętla zwrotna bez skonfigurowanej tożsamości MUST być odmową startu. Moduł nie
przechowuje hasła do żadnego serwera narzędzi i nie ma czego rotować.

Serwerów MAY być kilka i MUST być konfigurowane niezależnie od siebie: skonfigurowanie jednego
MUST NOT wymagać skonfigurowania drugiego, a błąd w ustawieniach jednego MUST nazywać ten
serwer, a nie „serwer narzędzi".

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem serwera narzędzi spoza pętli zwrotnej i
  bez skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie
- **AND** komunikat MUST nazywać serwer, którego dotyczy

#### Scenario: Pętla zwrotna bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem w pętli zwrotnej i bez tożsamości
- **THEN** startuje i łączy się z lokalnym serwerem narzędzi

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i adres w pętli zwrotnej
- **THEN** moduł MUST odmówić startu, zamiast wybrać jeden z nich

#### Scenario: Jeden serwer skonfigurowany, drugi nie

- **WHEN** moduł startuje z adresem jednego serwera narzędzi i bez adresu drugiego
- **THEN** startuje i korzysta z tego, który jest skonfigurowany
- **AND** brak drugiego MUST NOT być traktowany jako błąd konfiguracji

### Requirement: Brak serwera narzędzi nie odbiera agentowi mowy

Serwer narzędzi nieskonfigurowany, nieosiągalny albo odmawiający tożsamości MUST NOT
przeszkodzić modułowi wstać ani prowadzić rozmowy. Model MUST wtedy dostać turę bez narzędzi
tego serwera, a nie turę z narzędziami, które nie działają.

Serwery MUST być niedostępne niezależnie od siebie: niedostępność jednego MUST NOT zabrać
modelowi narzędzi drugiego, który odpowiada. Źródło narzędzi stojące w tym samym procesie
MUST być traktowane tak samo jak serwer, który odpowiada: jego narzędzia MUST docierać do
modelu niezależnie od tego, czy którykolwiek serwer sieciowy odpowiada.

Agent MUST powiedzieć operatorowi, że nie ma w tej chwili dostępu do danych albo do czynności,
o które ten prosi. MUST NOT przedstawić tego jako braku danych w archiwum, MUST NOT
przedstawić tego jako braku zespołu w katalogu i MUST NOT odpowiedzieć liczbą, której nie
dostał.

#### Scenario: Serwer narzędzi nie odpowiada

- **WHEN** moduł nie może nawiązać sesji z serwerem narzędzi, a operator pyta o cenę
- **THEN** agent odpowiada, że nie ma teraz dostępu do archiwum
- **AND** MUST NOT podać ceny ani stwierdzić, że archiwum jej nie ma

#### Scenario: Moduł startuje bez skonfigurowanego serwera narzędzi

- **WHEN** adres serwera narzędzi nie jest skonfigurowany
- **THEN** moduł startuje i prowadzi rozmowę bez narzędzi tego serwera

#### Scenario: Jeden serwer odpowiada, drugi nie

- **WHEN** jeden ze skonfigurowanych serwerów jest nieosiągalny, a drugi odpowiada
- **THEN** model dostaje narzędzia tego, który odpowiada
- **AND** o brakującym MUST zostać powiedziane, że jest niedostępny, gdy operator prosi o
  czynność, która go wymaga

#### Scenario: Żaden serwer sieciowy nie odpowiada

- **WHEN** żaden ze skonfigurowanych serwerów sieciowych nie odpowiada
- **THEN** model MUST dostać narzędzia źródła stojącego w tym samym procesie
- **AND** tura MUST się odbyć

#### Scenario: Operator prosi o zespół, a katalog odmawia

- **WHEN** operator prosi o założenie zespołu, a katalog zespołów odmawia — nazywając powód
- **THEN** agent przenosi ten powód operatorowi
- **AND** MUST NOT stwierdzić, że zespół powstał, ani opisać go tak, jakby powstał

### Requirement: Wołanie serwera narzędzi ma skończony czas

Każde wywołanie narzędzia MUST mieć górną granicę czasu oczekiwania. Po jej przekroczeniu
moduł MUST oddać modelowi wynik nazywający awarię dostępu, a nie czekać dłużej, niż
operator patrzący w panel jest gotów czekać.

Przekroczenie czasu MUST być odróżnialne od odmowy narzędzia: jedno mówi „nie udało się
zapytać", drugie „zapytano i odpowiedziano, że tak nie można".

#### Scenario: Narzędzie nie odpowiada w czasie

- **WHEN** wywołanie narzędzia przekracza wyznaczony czas
- **THEN** model dostaje wynik nazywający awarię dostępu do serwera narzędzi
- **AND** wynik ten MUST NOT czytać się jak odmowa narzędzia

### Requirement: Moduł nie trzyma kopii tego, co ogłasza serwer narzędzi

Nazwy narzędzi, ich opisy i kształty parametrów MUST pochodzić z sesji z serwerem, który je
publikuje, a nie z drugiej kopii trzymanej po tej stronie. Moduł MUST NOT importować kodu
serwera narzędzi stojącego w innym procesie.

Dla źródła narzędzi stojącego w tym samym procesie wymaganie jest spełnione z konstrukcji:
katalog jest tam, gdzie jego wykonanie, więc nie ma dwóch kopii do rozjechania. MUST NOT
powstać commitowana migawka takiego katalogu — sprawdzanie jej wobec samej siebie nie łapie
niczego, a mówi, że łapie.

#### Scenario: Narzędzie znika po stronie serwera

- **WHEN** serwer przestaje ogłaszać narzędzie
- **THEN** model przestaje je dostawać, bez zmiany w tym module

#### Scenario: Moduł nie ma czego sprawdzać przed startem

- **WHEN** moduł startuje
- **THEN** nie sprawdza żadnego commitowanego opisu narzędzi, bo takiego nie trzyma

#### Scenario: Narzędzie źródła lokalnego zmienia opis

- **WHEN** opis narzędzia publikowanego w tym samym procesie się zmienia
- **THEN** model dostaje nowy opis od razu
- **AND** MUST NOT istnieć plik, który trzeba było przy tym zaktualizować

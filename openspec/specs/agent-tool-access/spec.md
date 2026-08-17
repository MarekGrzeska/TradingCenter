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
modelowi narzędzi drugiego, który odpowiada.

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
- **THEN** moduł startuje i prowadzi rozmowę bez narzędzi

#### Scenario: Jeden serwer odpowiada, drugi nie

- **WHEN** jeden ze skonfigurowanych serwerów jest nieosiągalny, a drugi odpowiada
- **THEN** model dostaje narzędzia tego, który odpowiada
- **AND** o brakującym MUST zostać powiedziane, że jest niedostępny, gdy operator prosi o
  czynność, która go wymaga

#### Scenario: Operator prosi o zespół przy nieosiągalnym katalogu

- **WHEN** serwer narzędzi do zespołów jest nieosiągalny, a operator prosi o założenie zespołu
- **THEN** agent mówi, że nie ma teraz dostępu do katalogu zespołów
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

Moduł MUST NOT importować kodu serwera narzędzi ani żadnego innego modułu. Nazwy
narzędzi, ich opisy i kształty parametrów MUST pochodzić z sesji z serwerem, a nie z
pliku w tym module.

Kontrakt jedzie tu w tej samej sesji, w której jest używany, więc nie ma dwóch kopii do
rozjechania i MUST NOT powstać trzecia w postaci wpisanej na stałe listy.

#### Scenario: Narzędzie znika po stronie serwera

- **WHEN** serwer przestaje ogłaszać narzędzie
- **THEN** model przestaje je dostawać, bez zmiany w tym module

#### Scenario: Moduł nie ma czego sprawdzać przed startem

- **WHEN** moduł startuje
- **THEN** nie sprawdza żadnego commitowanego opisu narzędzi, bo takiego nie trzyma


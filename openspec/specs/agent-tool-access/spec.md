# agent-tool-access Specification

## Purpose

Warunki, na jakich moduł łączy się z serwerem narzędzi: czym się przed nim przedstawia,
jak długo czeka, co robi, gdy serwera nie ma, i dlaczego nie trzyma u siebie kopii tego,
co tamten publikuje.

## Requirements

### Requirement: Tryb połączenia z serwerem narzędzi jest wybrany jednoznacznie

Konfiguracja MUST wskazywać dokładnie jeden tryb dostępu do serwera narzędzi: tożsamość
wobec adresu zdalnego albo pętla zwrotna bez niej. Konfiguracja nazywająca oba tryby
naraz MUST być odrzucona przy starcie, zanim moduł zacznie odpowiadać na cokolwiek.

Adres inny niż pętla zwrotna bez skonfigurowanej tożsamości MUST być odmową startu.
Moduł nie przechowuje hasła do serwera narzędzi i nie ma czego rotować.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem serwera narzędzi spoza pętli zwrotnej i
  bez skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Pętla zwrotna bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem w pętli zwrotnej i bez tożsamości
- **THEN** startuje i łączy się z lokalnym serwerem narzędzi

#### Scenario: Oba tryby naraz

- **WHEN** konfiguracja niesie i tożsamość, i adres w pętli zwrotnej
- **THEN** moduł MUST odmówić startu, zamiast wybrać jeden z nich

### Requirement: Brak serwera narzędzi nie odbiera agentowi mowy

Serwer narzędzi nieskonfigurowany, nieosiągalny albo odmawiający tożsamości MUST NOT
przeszkodzić modułowi wstać ani prowadzić rozmowy. Model MUST wtedy dostać turę bez
narzędzi, a nie turę z narzędziami, które nie działają.

Agent MUST powiedzieć operatorowi, że nie ma w tej chwili dostępu do danych, o które ten
pyta. MUST NOT przedstawić tego jako braku danych w archiwum i MUST NOT odpowiedzieć
liczbą, której nie dostał.

#### Scenario: Serwer narzędzi nie odpowiada

- **WHEN** moduł nie może nawiązać sesji z serwerem narzędzi, a operator pyta o cenę
- **THEN** agent odpowiada, że nie ma teraz dostępu do archiwum
- **AND** MUST NOT podać ceny ani stwierdzić, że archiwum jej nie ma

#### Scenario: Moduł startuje bez skonfigurowanego serwera narzędzi

- **WHEN** adres serwera narzędzi nie jest skonfigurowany
- **THEN** moduł startuje i prowadzi rozmowę bez narzędzi

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

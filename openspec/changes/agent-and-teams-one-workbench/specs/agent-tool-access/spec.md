## MODIFIED Requirements

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

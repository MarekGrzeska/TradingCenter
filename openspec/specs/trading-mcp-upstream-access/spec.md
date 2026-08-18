# trading-mcp-upstream-access Specification

## Purpose
Jak moduł dochodzi do `capital-gateway`: czym się przed nim przedstawia, dlaczego bez tego
poświadczenia nie wstaje i skąd wie, że rachunek, na którym ma handlować, jest rachunkiem
demonstracyjnym.
## Requirements
### Requirement: Bez poświadczenia do gatewaya moduł nie wstaje

Moduł MUST odmówić startu, gdy poświadczenie wymagane przez `capital-gateway` nie zostało
skonfigurowane, i MUST NOT wstawać w trybie, w którym gateway jest wołany bez niego. Odmowa
MUST nazywać brakujące ustawienie.

Moduł bez poświadczenia nie jest modułem ograniczonym do odczytu — jest modułem, którego każde
narzędzie odpowiada tym samym błędem, i którego awarię widać dopiero w środku przebiegu.

#### Scenario: Start bez skonfigurowanego poświadczenia

- **WHEN** moduł startuje bez poświadczenia do gatewaya
- **THEN** odmawia startu z komunikatem nazywającym brakujące ustawienie
- **AND** nie zaczyna nasłuchiwać

### Requirement: Poświadczenie do gatewaya jest wymagane niezależnie od adresu

`capital-gateway` przyjmuje wywołania wyłącznie z własnym poświadczeniem dołączonym do
każdego żądania — jego wymóg nie zależy od tego, czy gateway stoi na tej samej maszynie, czy
zdalnie. Konfiguracja tego modułu MUST nieść to poświadczenie przy każdym adresie gatewaya,
loopback nie wyłącza go.

To inny kształt niż tryb dostępu do serwera narzędzi (`teams-tool-access`): tam pętla
zwrotna bez tożsamości jest poprawnym trybem, bo Easy Auth stoi tylko przed zdalną
instancją. Gateway żąda tego samego nagłówka od każdego wołającego, więc nie ma tu trybu do
wybierania.

#### Scenario: Poświadczenie nieskonfigurowane przy adresie loopback

- **WHEN** moduł startuje z adresem gatewaya w pętli zwrotnej i bez skonfigurowanego
  poświadczenia
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

### Requirement: Moduł pracuje wyłącznie na rachunku demonstracyjnym

Moduł MUST sprawdzić u gatewaya, w jakim środowisku ten pracuje, zanim otworzy port, i MUST
odmówić startu, gdy odpowiedź nie nazywa środowiska demonstracyjnego. Sprawdzenie MUST
poprzedzać obsłużenie pierwszego narzędzia — zapisującego i czytającego tak samo, bo przed
otwarciem portu nie ma jeszcze żadnego wywołującego.

Nie SHALL istnieć ustawienie, przełącznik ani tryb, który dopuszcza pracę na rachunku
rzeczywistym. Środowisko MUST być wzięte z odpowiedzi gatewaya, a MUST NOT być wzięte z
konfiguracji tego modułu — konfiguracja mówi, w co wierzy operator, a odpowiedź mówi, do
czego moduł jest naprawdę podłączony.

Odpowiedź gatewaya MUST nazywać środowisko wynikające z wiązania samego gatewaya. Wartość,
która nie może być inna niż `demo`, nie jest odpowiedzią na to pytanie, tylko jego
powtórzeniem — a sprawdzenie porównujące się z taką wartością nie umie wykryć tego, przed
czym stoi.

#### Scenario: Gateway nie zgłasza środowiska demonstracyjnego

- **WHEN** moduł startuje, a gateway zgłasza środowisko inne niż demonstracyjne
- **THEN** moduł odmawia startu, nazywając środowisko jako przyczynę
- **AND** nie zaczyna nasłuchiwać, więc żadne narzędzie nie zostaje obsłużone

#### Scenario: Gateway nie odpowiada przy starcie

- **WHEN** moduł startuje, a gateway nie odpowiada na pytanie o środowisko
- **THEN** moduł odmawia startu, nazywając nieosiągalny gateway jako przyczynę
- **AND** MUST NOT wstać w trybie, w którym środowisko pozostaje niesprawdzone

### Requirement: Poświadczenie do gatewaya nie wychodzi poza moduł

Moduł MUST NOT umieszczać poświadczenia do gatewaya w logach, w odpowiedziach narzędzi ani w
komunikatach błędów. Wynik nieudanego wywołania MUST nazywać rodzaj niepowodzenia, a MUST NOT
nieść poświadczenia ani jego fragmentu.

#### Scenario: Gateway odrzuca poświadczenie

- **WHEN** gateway odpowiada odmową uwierzytelnienia
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** ani odpowiedź, ani log nie niosą poświadczenia


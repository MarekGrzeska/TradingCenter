# trading-mcp-upstream-access Specification

## Purpose
Jak moduł dochodzi do `capital-gateway`: czym się przed nim przedstawia, dlaczego bez tego
poświadczenia nie wstaje i skąd wie, że rachunek, na którym ma handlować, jest rachunkiem
demonstracyjnym.
## Requirements
### Requirement: Bez poświadczenia do gatewaya moduł nie wstaje

Moduł MUST odmówić startu, gdy nie może przedstawić się gatewayowi, i MUST NOT wstawać w trybie, w
którym gateway jest wołany bez poświadczenia. Odmowa MUST nazywać, czego zabrakło.

Brakiem poświadczenia jest nieskonfigurowany klucz współdzielony — to MUST być odmowa startu, nie
ostrzeżenie. Moduł bez klucza nie jest modułem ograniczonym do odczytu, jest modułem, którego każde
narzędzie odpowiada tym samym błędem, i którego awarię widać dopiero w środku przebiegu.

Nieudane uzyskanie tokenu MUST NOT być samo w sobie odmową startu. O tym, czy moduł może się
przedstawić, rozstrzyga gateway, a nie katalog: moduł MUST wysłać żądanie tym, co ma, i MUST
odmówić otwarcia portu, gdy gateway odrzuci sprawdzenie środowiska, które ten moduł wykonuje przed
nasłuchem. Reguła oparta na katalogu zatrzymywałaby moduł z powodu poświadczenia, którego gateway
w danym momencie może wcale nie wymagać.

#### Scenario: Start bez skonfigurowanego poświadczenia

- **WHEN** moduł startuje bez poświadczenia do gatewaya
- **THEN** odmawia startu z komunikatem nazywającym brakujące ustawienie
- **AND** nie zaczyna nasłuchiwać

#### Scenario: Tokenu nie udało się uzyskać, gateway jeszcze go nie wymaga

- **WHEN** moduł nie może uzyskać tokenu, a gateway odpowiada na sprawdzenie środowiska
- **THEN** moduł startuje i pracuje na kluczu współdzielonym

#### Scenario: Gateway odrzuca sprawdzenie środowiska

- **WHEN** gateway odrzuca sprawdzenie środowiska wykonywane przed otwarciem portu
- **THEN** moduł nie zaczyna nasłuchiwać

### Requirement: Poświadczenie do gatewaya jest wymagane niezależnie od adresu

`capital-gateway` przyjmuje wywołania wyłącznie z poświadczeniem dołączonym do każdego żądania —
jego wymóg nie zależy od tego, czy gateway stoi na tej samej maszynie, czy zdalnie. Konfiguracja
tego modułu MUST nieść poświadczenie przy każdym adresie gatewaya, loopback nie wyłącza go.

Postać poświadczenia zależy od miejsca, jego wymóg nie: token tożsamości modułu tam, gdzie moduł ją
ma, klucz współdzielony tam, gdzie nie ma. To wciąż inny kształt niż tryb dostępu do serwera
narzędzi (`teams-tool-access`), gdzie pętla zwrotna bez tożsamości jest poprawnym trybem, bo
uwierzytelnianie stoi tylko przed zdalną instancją. Gateway żąda poświadczenia od każdego
wołającego, więc nie ma tu trybu do wybierania — jest tylko postać do rozpoznania.

#### Scenario: Poświadczenie nieskonfigurowane przy adresie loopback

- **WHEN** moduł startuje z adresem gatewaya w pętli zwrotnej i bez skonfigurowanego
  poświadczenia
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

#### Scenario: Gateway zdalny, tożsamość własna

- **WHEN** moduł stoi tam, gdzie ma własną tożsamość, i woła gateway pod adresem zdalnym
- **THEN** każde żądanie niesie token tej tożsamości wystawiony dla gatewaya

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


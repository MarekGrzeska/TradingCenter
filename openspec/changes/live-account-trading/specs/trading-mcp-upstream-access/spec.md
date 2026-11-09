## RENAMED Requirements

- FROM: `### Requirement: Moduł pracuje wyłącznie na rachunku demonstracyjnym`
- TO: `### Requirement: Moduł pracuje na środowisku, dla którego go uruchomiono, potwierdzonym przez gateway`

## MODIFIED Requirements

### Requirement: Moduł pracuje na środowisku, dla którego go uruchomiono, potwierdzonym przez gateway

Konfiguracja modułu MUST nazywać środowisko, którego się spodziewa: demonstracyjne, gdy nie nazywa żadnego, albo
realne, gdy nazywa je jawnie. Moduł MUST sprawdzić u gatewaya, w jakim środowisku ten pracuje, zanim otworzy port, i
MUST odmówić startu, gdy odpowiedź nie nazywa środowiska, którego moduł się spodziewa — w obie strony: instancja demo
przy gatewayu realnym i instancja realna przy gatewayu demo nie wstają. Sprawdzenie MUST poprzedzać obsłużenie
pierwszego narzędzia — zapisującego i czytającego tak samo, bo przed otwarciem portu nie ma jeszcze żadnego wołającego.

Środowisko, na którym moduł pracuje, MUST być wzięte z odpowiedzi gatewaya, a MUST NOT być wzięte z konfiguracji tego
modułu — konfiguracja mówi, czego operator się spodziewa, a odpowiedź mówi, do czego moduł jest naprawdę podłączony.
Ustawienie oczekiwanego środowiska MUST NOT być w stanie samo przenieść modułu na rachunek rzeczywisty: bez gatewaya
związanego z hostem realnym instancja realna nie wstaje.

Odpowiedź gatewaya MUST nazywać środowisko wynikające z wiązania samego gatewaya. Wartość,
która nie może być inna niż oczekiwana, nie jest odpowiedzią na to pytanie, tylko jego
powtórzeniem — a sprawdzenie porównujące się z taką wartością nie umie wykryć tego, przed
czym stoi.

#### Scenario: Gateway nie zgłasza środowiska demonstracyjnego

- **WHEN** instancja demo startuje, a gateway zgłasza środowisko inne niż demonstracyjne
- **THEN** moduł odmawia startu, nazywając środowisko jako przyczynę
- **AND** nie zaczyna nasłuchiwać, więc żadne narzędzie nie zostaje obsłużone

#### Scenario: Gateway nie odpowiada przy starcie

- **WHEN** moduł startuje, a gateway nie odpowiada na pytanie o środowisko
- **THEN** moduł odmawia startu, nazywając nieosiągalny gateway jako przyczynę
- **AND** MUST NOT wstać w trybie, w którym środowisko pozostaje niesprawdzone

#### Scenario: Instancja realna przy gatewayu demo

- **WHEN** instancja, która spodziewa się środowiska realnego, startuje, a gateway zgłasza środowisko demonstracyjne
- **THEN** moduł odmawia startu, nazywając oba środowiska

#### Scenario: Wartość oczekiwanego środowiska spoza listy

- **WHEN** konfiguracja nazywa oczekiwane środowisko inne niż demonstracyjne albo realne
- **THEN** moduł odmawia startu, zanim zapyta gatewaya

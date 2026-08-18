## MODIFIED Requirements

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

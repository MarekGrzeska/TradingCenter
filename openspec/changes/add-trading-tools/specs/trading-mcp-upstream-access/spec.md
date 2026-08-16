## Purpose

Jak moduł dochodzi do `capital-gateway`: czym się przed nim przedstawia, dlaczego bez tego
poświadczenia nie wstaje i skąd wie, że rachunek, na którym ma handlować, jest rachunkiem
demonstracyjnym.

## ADDED Requirements

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

### Requirement: Tryb dostępu do gatewaya jest wybrany jednoznacznie

Konfiguracja MUST wskazywać dokładnie jeden tryb dostępu: adres zdalny wraz z tożsamością,
którą moduł się przedstawia, albo pętlę zwrotną bez niej. Konfiguracja nazywająca oba tryby
naraz albo adres zdalny bez tożsamości MUST być odrzucona przy starcie.

#### Scenario: Adres zdalny bez tożsamości

- **WHEN** moduł startuje ze wskazanym adresem gatewaya spoza pętli zwrotnej i bez
  skonfigurowanej tożsamości
- **THEN** MUST odmówić startu z komunikatem nazywającym brakujące ustawienie

### Requirement: Moduł pracuje wyłącznie na rachunku demonstracyjnym

Moduł MUST sprawdzić u gatewaya, w jakim środowisku ten pracuje, zanim obsłuży pierwsze
narzędzie zapisujące, i MUST odmówić startu, gdy odpowiedź nie nazywa środowiska
demonstracyjnego. Sprawdzenie MUST powtórzyć się po każdym odzyskaniu połączenia z gatewayem,
zanim moduł znów obsłuży narzędzie zapisujące.

Nie SHALL istnieć ustawienie, przełącznik ani tryb, który dopuszcza pracę na rachunku
rzeczywistym. Środowisko MUST być wzięte z odpowiedzi gatewaya, a MUST NOT być wzięte z
konfiguracji tego modułu — konfiguracja mówi, w co wierzy operator, a odpowiedź mówi, do czego
moduł jest naprawdę podłączony.

#### Scenario: Gateway nie zgłasza środowiska demonstracyjnego

- **WHEN** moduł startuje, a gateway zgłasza środowisko inne niż demonstracyjne
- **THEN** moduł odmawia startu, nazywając środowisko jako przyczynę
- **AND** żadne narzędzie zapisujące nie zostaje obsłużone

#### Scenario: Gateway zmienia środowisko przy odzyskanym połączeniu

- **WHEN** moduł traci połączenie z gatewayem, a po jego odzyskaniu gateway zgłasza środowisko
  inne niż demonstracyjne
- **THEN** moduł przestaje obsługiwać narzędzia zapisujące
- **AND** wywołujący dostaje odmowę nazywającą środowisko

### Requirement: Poświadczenie do gatewaya nie wychodzi poza moduł

Moduł MUST NOT umieszczać poświadczenia do gatewaya w logach, w odpowiedziach narzędzi ani w
komunikatach błędów. Wynik nieudanego wywołania MUST nazywać rodzaj niepowodzenia, a MUST NOT
nieść poświadczenia ani jego fragmentu.

#### Scenario: Gateway odrzuca poświadczenie

- **WHEN** gateway odpowiada odmową uwierzytelnienia
- **THEN** model dostaje wynik nazywający awarię dostępu
- **AND** ani odpowiedź, ani log nie niosą poświadczenia

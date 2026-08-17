# trading-mcp-transport Specification

## Purpose
Czym moduł jest wystawiony na zewnątrz: jednym transportem sieciowym, imienną listą wołających
i sondą zdrowia, którą platforma sprawdza bez otwierania sesji MCP.
## Requirements
### Requirement: Moduł wystawia jeden transport i jest nim transport sieciowy

Moduł MUST wystawiać narzędzia wyłącznie transportem sieciowym MCP. MUST NOT wystawiać
transportu uruchamianego jako proces lokalny klienta.

Transport lokalny nie niesie tożsamości wołającego — jest nim ten, kto uruchomił proces. Przy
zestawie wyłącznie czytającym to jest wygoda operatora; przy zestawie ruszającym rachunek
oznaczałoby to, że każdy klient MCP na maszynie operatora handluje, a lista uprawnionych
przestaje cokolwiek znaczyć.

#### Scenario: Klient próbuje transportu lokalnego

- **WHEN** klient MCP próbuje uruchomić moduł jako proces lokalny
- **THEN** moduł nie udostępnia takiego trybu

### Requirement: Wołający jest wskazany imiennie

Gdy moduł stoi w miejscu osiągalnym z sieci, MUST przyjmować wywołania wyłącznie od
wywołujących wskazanych imiennie w konfiguracji dostępu. Żądanie bez ustalonej tożsamości
MUST zostać odrzucone, zanim dojdzie do narzędzia.

Lista MUST być listą wyliczoną, a MUST NOT być regułą typu „każdy uwierzytelniony w
katalogu". Moduł składający zlecenia ma tylu wołających, ilu wymieniono, i dopisanie kolejnego
ma być decyzją, nie skutkiem ubocznym.

#### Scenario: Wywołanie bez ustalonej tożsamości

- **WHEN** przychodzi żądanie z sieci bez ustalonej tożsamości wołającego
- **THEN** moduł odrzuca je bez wywołania narzędzia

#### Scenario: Wywołanie od modułu spoza listy

- **WHEN** żądanie przychodzi z tożsamości, której lista uprawnionych nie wymienia
- **THEN** moduł odrzuca je
- **AND** odpowiedź nie ujawnia, co moduł publikuje

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP

Moduł MUST wystawiać sondę zdrowia osiągalną bez otwierania sesji MCP i bez poświadczenia.
Sonda MUST odpowiadać wyłącznie stanem modułu i MUST NOT ujawniać stanu rachunku, nazwy konta,
środowiska providera ani listy narzędzi.

Platforma restartuje kontener na podstawie tej sondy, a nie mówi protokołem MCP.

#### Scenario: Platforma odpytuje sondę

- **WHEN** przychodzi żądanie na trasę sondy zdrowia bez poświadczenia
- **THEN** moduł odpowiada stanem swojej żywotności
- **AND** odpowiedź nie niesie niczego o rachunku ani o narzędziach


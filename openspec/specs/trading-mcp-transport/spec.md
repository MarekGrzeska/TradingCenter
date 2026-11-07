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

Wołających jest dwóch rodzajów i każdy przedstawia się inaczej. Usługa z sieci wewnętrznej
(workbench) MUST przedstawić klucz współdzielony. Wołający z zewnątrz MUST przedstawić ważny
token Entra wydany dla API bramy, wydany aplikacji wymienionej na liście zewnętrznych wołających,
dla osoby z rolą `admin`. Pusta lista zewnętrznych wołających MUST oznaczać, że nic z zewnątrz
nie jest wpuszczane, cokolwiek przedstawi.

#### Scenario: Wywołanie bez ustalonej tożsamości

- **WHEN** przychodzi żądanie z sieci bez ustalonej tożsamości wołającego
- **THEN** moduł odrzuca je bez wywołania narzędzia

#### Scenario: Wywołanie od modułu spoza listy

- **WHEN** żądanie przychodzi z tożsamości, której lista uprawnionych nie wymienia
- **THEN** moduł odrzuca je
- **AND** odpowiedź nie ujawnia, co moduł publikuje

#### Scenario: Token aplikacji spoza listy zewnętrznych wołających

- **WHEN** żądanie z zewnątrz niesie ważny token admina wydany aplikacji, której lista zewnętrznych wołających nie wymienia
- **THEN** moduł odrzuca je z 403 bez wywołania narzędzia

#### Scenario: Pusta lista zewnętrznych wołających

- **WHEN** lista zewnętrznych wołających jest pusta, a żądanie z zewnątrz niesie dowolny token
- **THEN** moduł odrzuca je bez wywołania narzędzia

### Requirement: Zdrowie modułu da się sprawdzić bez sesji MCP

Moduł MUST wystawiać sondę zdrowia osiągalną bez otwierania sesji MCP i bez poświadczenia.
Sonda MUST odpowiadać wyłącznie stanem modułu i MUST NOT ujawniać stanu rachunku, nazwy konta,
środowiska providera ani listy narzędzi.

Platforma restartuje kontener na podstawie tej sondy, a nie mówi protokołem MCP.

#### Scenario: Platforma odpytuje sondę

- **WHEN** przychodzi żądanie na trasę sondy zdrowia bez poświadczenia
- **THEN** moduł odpowiada stanem swojej żywotności
- **AND** odpowiedź nie niesie niczego o rachunku ani o narzędziach

### Requirement: Zapis od wołającego z zewnątrz zostawia ślad w logu

Wywołanie narzędzia zmieniającego stan rachunku, które przyszło od wołającego z tokenem, MUST zostawić wpis w logu
**przed** wysłaniem do bramy, nazywający czynność wysyłaną do bramy (metodę i ścieżkę), jej treść, aplikację i
osobę, oraz drugi wpis ze skutkiem —
rozliczonym, nierozliczonym, odmową albo nieznanym — gdy ten wróci. Wpis MUST NOT nieść tokenu ani klucza.

Rozmowa trzyma ślad zlecenia w swojej bazie (`agent-trading`); wołający z zewnątrz omija rozmowę, więc jedynym śladem po
stronie systemu jest ten wpis.

#### Scenario: Zlecenie złożone z klienta operatora

- **WHEN** wołający z tokenem woła `place_order`
- **THEN** przed wysłaniem do bramy w logu jest wpis z czynnością, jej treścią, aplikacją i osobą
- **AND** po odpowiedzi bramy jest wpis ze skutkiem

#### Scenario: Brama nie odpowiada

- **WHEN** wywołanie zapisujące od wołającego z tokenem kończy się błędem dostępu do bramy
- **THEN** wpis skutku nazywa skutek nieznanym, a nie nieudanym


## Purpose

Opisuje, kto ma prawo wywołać `capital-gateway` i czego moduł o sobie nie ujawnia, gdy stoi w miejscu
osiągalnym z sieci — czyli warstwę przed wszystkim, co moduł robi z providerem.

## ADDED Requirements

### Requirement: Każde wywołanie niesie poświadczenie

Moduł wystawia trasy, które składają zlecenia i zamykają pozycje. MUST wymagać poświadczenia od
każdego wywołującego — na trasach HTTP i przy zestawianiu połączenia WebSocket. Wywołanie bez
poświadczenia albo z poświadczeniem nieuznanym MUST zostać odrzucone przed dotknięciem providera,
odpowiedzią `401`.

Ograniczenia dostępu po stronie platformy MUST NOT być traktowane jako spełnienie tego wymagania.
Są warstwą dodatkową, konfigurowaną osobno i osobno psowalną.

#### Scenario: Żądanie bez poświadczenia

- **WHEN** przychodzi żądanie na dowolną trasę modułu poza sondą zdrowia, bez poświadczenia
- **THEN** moduł odpowiada `401`
- **AND** nie wykonuje żadnego wywołania do providera

#### Scenario: Żądanie z nieuznanym poświadczeniem

- **WHEN** przychodzi żądanie z poświadczeniem, którego moduł nie uznaje
- **THEN** moduł odpowiada `401`
- **AND** odpowiedź nie rozróżnia poświadczenia nieistniejącego od błędnego

#### Scenario: Zestawienie WebSocketa bez poświadczenia

- **WHEN** konsument zestawia połączenie WebSocket bez poświadczenia
- **THEN** moduł odmawia zestawienia połączenia
- **AND** nie zapisuje konsumenta do rozgłaszania

### Requirement: Bez skonfigurowanego poświadczenia moduł nie wstaje

Moduł uruchomiony bez skonfigurowanego poświadczenia byłby otwartym endpointem handlowym, a brak
konfiguracji nie objawiłby się niczym widocznym. Moduł MUST odmówić startu, gdy poświadczenia nie
skonfigurowano. MUST NOT wstawać w trybie, w którym uwierzytelnianie jest wyłączone.

#### Scenario: Start bez konfiguracji

- **WHEN** moduł startuje bez skonfigurowanego poświadczenia
- **THEN** odmawia startu z komunikatem wskazującym brakującą konfigurację
- **AND** nie zaczyna nasłuchiwać na żadnym porcie

### Requirement: Sonda zdrowia jest jedynym wyjątkiem

Platforma hostująca sprawdza żywotność aplikacji bez żadnego poświadczenia i na tej podstawie
decyduje o restarcie. Dokładnie jedna trasa MUST być osiągalna bez uwierzytelnienia i MUST
odpowiadać wyłącznie stanem modułu. MUST NOT ujawniać nazwy konta, stanu sesji z providerem,
listy tras ani wersji zależności.

#### Scenario: Platforma odpytuje sondę

- **WHEN** przychodzi żądanie na trasę sondy zdrowia bez poświadczenia
- **THEN** moduł odpowiada stanem swojej żywotności
- **AND** odpowiedź nie niesie żadnej informacji o koncie, sesji ani konfiguracji

### Requirement: Na produkcji moduł nie publikuje swojego API

Interaktywna dokumentacja i schemat OpenAPI podają gotową mapę tras razem z tymi handlowymi.
Na produkcji moduł MUST NOT wystawiać ani interaktywnej dokumentacji, ani schematu OpenAPI.
Poza produkcją MUST je wystawiać — na nich opiera się generowanie kontraktu dla konsumentów.

#### Scenario: Odpytanie o dokumentację na produkcji

- **WHEN** żądanie trafia na ścieżkę dokumentacji lub schematu OpenAPI w konfiguracji produkcyjnej
- **THEN** moduł odpowiada `404`

#### Scenario: Odpytanie o schemat poza produkcją

- **WHEN** żądanie trafia na ścieżkę schematu OpenAPI w konfiguracji nieprodukcyjnej
- **THEN** moduł zwraca schemat
- **AND** generowanie kontraktu z tego schematu działa jak dotąd

### Requirement: Poświadczenie wywołującego nie trafia do logów

Moduł loguje żądania, a poświadczenie przychodzi w każdym z nich. Moduł MUST NOT umieszczać
poświadczenia wywołującego w logach, komunikatach błędów ani odpowiedziach.

#### Scenario: Odrzucone żądanie trafia do logu

- **WHEN** moduł odrzuca żądanie z powodu poświadczenia i loguje to zdarzenie
- **THEN** log niesie ścieżkę, metodę i powód odrzucenia
- **AND** nie niesie poświadczenia ani jego fragmentu

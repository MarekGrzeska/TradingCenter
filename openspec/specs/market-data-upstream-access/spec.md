# market-data-upstream-access Specification

## Purpose
Opisuje, czym `market-data` przedstawia się swojemu jedynemu upstreamowi, gdy ten zaczyna wymagać
poświadczenia, i jak odróżnia odmowę dostępu od braku danych.
## Requirements
### Requirement: Ruch do gatewaya niesie poświadczenie

Moduł sięga do `capital-gateway` po historię, po katalog instrumentów i po strumień na żywo.
Każde z tych wywołań MUST nieść poświadczenie modułu — zarówno żądania REST, jak i zestawienie
połączenia WebSocket.

Poświadczenie ma dwie postacie i wybiera je środowisko, nie ustawienie. Tam, gdzie moduł ma własną
tożsamość w katalogu, MUST przedstawić się **tokenem tej tożsamości**, wystawionym dla gatewaya
jako odbiorcy. Tam, gdzie tożsamości nie ma — praca lokalna — MUST posłużyć się kluczem
współdzielonym, tak jak dotąd. Token jest poświadczeniem, którego nie da się skopiować z pliku
konfiguracyjnego jednego modułu do drugiego, i to jest powód, dla którego zastępuje klucz wszędzie,
gdzie jest dostępny.

Zestawienie strumienia MUST nieść poświadczenie niezależnie od tego, czy warstwa uwierzytelniająca
przed gatewayem obejmuje trasę strumienia — sprawdzenie wewnątrz gatewaya jest tu jedynym, które
działa, i moduł MUST NOT polegać na tym, że zrobi to platforma.

#### Scenario: Uzupełnianie wstecz sięga po historię

- **WHEN** moduł wykonuje żądanie do gatewaya po historię świec
- **THEN** żądanie niesie poświadczenie modułu

#### Scenario: Nasłuch zestawia strumień

- **WHEN** moduł zestawia połączenie WebSocket do gatewaya
- **THEN** zestawienie niesie poświadczenie modułu

#### Scenario: Moduł z własną tożsamością przedstawia token

- **WHEN** moduł pracuje tam, gdzie ma własną tożsamość w katalogu
- **THEN** żądania do gatewaya niosą token tej tożsamości, wystawiony dla gatewaya jako odbiorcy

#### Scenario: Praca lokalna bez katalogu

- **WHEN** moduł pracuje bez własnej tożsamości w katalogu
- **THEN** żądania do gatewaya niosą klucz współdzielony
- **AND** brak tożsamości nie jest awarią ani trybem obniżonym

### Requirement: Bez poświadczenia moduł nie wstaje

Moduł, który wstałby bez skonfigurowanego poświadczenia, wyglądałby na zdrowy i odpowiadał na
własnych trasach, a jego archiwum przestałoby rosnąć — objaw pojawiłby się dopiero przy odczycie,
godziny później. Moduł MUST odmówić startu, gdy poświadczenia do gatewaya nie skonfigurowano.

#### Scenario: Start bez konfiguracji

- **WHEN** moduł startuje bez skonfigurowanego poświadczenia do gatewaya
- **THEN** odmawia startu z komunikatem wskazującym brakującą konfigurację

### Requirement: Odmowa dostępu jest raportowana jako odmowa, nie jako brak danych

Gateway odrzucający wywołanie z powodu poświadczenia zwraca odpowiedź, którą łatwo pomylić z pustym
wynikiem. Moduł MUST odróżnić odmowę dostępu od braku danych: MUST NOT zapisać takiej odpowiedzi
jako pokrycia i MUST NOT oznaczyć okresu jako zebranego.

#### Scenario: Gateway odmawia w trakcie uzupełniania

- **WHEN** gateway odrzuca żądanie modułu z powodu poświadczenia
- **THEN** moduł raportuje porażkę wskazującą dostęp jako przyczynę
- **AND** pokrycie zakresu, którego dotyczyło żądanie, pozostaje niezmienione

#### Scenario: Gateway odmawia przy zestawianiu strumienia

- **WHEN** gateway odrzuca zestawienie połączenia WebSocket z powodu poświadczenia
- **THEN** moduł nie raportuje się jako zdrowy
- **AND** nie ponawia w nieskończoność bez zgłoszenia przyczyny

### Requirement: Poświadczenie do gatewaya nie trafia do logów

Moduł loguje adresy i porażki wywołań do upstreamu. MUST NOT umieszczać w logach, komunikatach
błędów ani we własnych odpowiedziach poświadczenia, którym przedstawia się gatewayowi.

#### Scenario: Nieudane wywołanie trafia do logu

- **WHEN** wywołanie do gatewaya kończy się błędem, a moduł loguje jego okoliczności
- **THEN** log niesie adres i kod odpowiedzi
- **AND** nie niesie poświadczenia ani jego fragmentu

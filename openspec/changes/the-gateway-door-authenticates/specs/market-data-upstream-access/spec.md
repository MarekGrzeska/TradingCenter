## MODIFIED Requirements

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

## MODIFIED Requirements

### Requirement: Wiadomość jest adresowana nazwą

Wywołujący MUST adresować wiadomość nazwą adresata, którą zna z listy, oraz — gdy adresat jest związany przez więcej niż
jednego bota — botem, przez którego ma pójść. Gdy adresat ma dokładnie jedno wiązanie, bot MAY zostać pominięty i
wiadomość MUST pójść przez to wiązanie. Gdy ma kilka, a bota pominięto, moduł MUST odmówić i wymienić boty; MUST NOT
wybierać żadnego z nich. Kontrakt MUST NOT przyjmować celu ani identyfikatora czatu.

Identyfikator czatu jest liczbą, którą każdy wywołujący musiałby skądś mieć i trzymać u siebie. Bot jest częścią decyzji
wywołującego (reguły pakietu alertów), więc jego wymiana ma unieważnić dokładnie to, co go wskazuje, a nie wszystko
naraz ani nic.

#### Scenario: Nieznany adresat

- **WHEN** wywołujący adresuje wiadomość nazwą, której moduł nie zna
- **THEN** moduł MUST odmówić, wskazując nazwę, i MUST NOT wysłać niczego

#### Scenario: Wiadomość z celem

- **WHEN** wywołujący podaje cel zamiast nazwy adresata
- **THEN** moduł MUST odmówić i MUST NOT wysłać niczego

#### Scenario: Wiadomość przez wskazanego bota

- **WHEN** adresat ma dwa wiązania i wywołujący wskazuje jednego z botów
- **THEN** wiadomość MUST pójść tylko przez to wiązanie

#### Scenario: Dwuznaczny adresat

- **WHEN** adresat ma dwa wiązania, a wywołujący nie wskazuje bota
- **THEN** moduł MUST odmówić, wymienić oba boty i MUST NOT wysłać niczego

#### Scenario: Bot, którego adresat nie ma

- **WHEN** wywołujący wskazuje bota, przez którego adresat nie jest związany
- **THEN** moduł MUST odmówić, wskazując bota i adresata, i MUST NOT wysłać niczego

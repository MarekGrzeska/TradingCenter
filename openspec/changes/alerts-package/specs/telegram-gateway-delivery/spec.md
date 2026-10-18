## MODIFIED Requirements

### Requirement: Wiadomość jest adresowana nazwą

Wywołujący MUST adresować wiadomość nazwą adresata, którą zna z listy. Kontrakt MUST NOT przyjmować
celu, identyfikatora czatu ani nazwy bota od wywołującego.

Identyfikator czatu jest liczbą, którą każdy wywołujący musiałby skądś mieć i trzymać u siebie, a
wymiana bota unieważniałaby wszystkie te kopie naraz. Kto słyszy jakie zdarzenie, decydują reguły
pakietu alertów, które nazywają adresata.

#### Scenario: Nieznany adresat

- **WHEN** wywołujący adresuje wiadomość nazwą adresata, której moduł nie zna
- **THEN** moduł MUST odmówić, wskazując nazwę, i MUST NOT wysłać niczego

#### Scenario: Wiadomość z celem

- **WHEN** wywołujący podaje cel zamiast nazwy adresata
- **THEN** moduł MUST odmówić i MUST NOT wysłać niczego

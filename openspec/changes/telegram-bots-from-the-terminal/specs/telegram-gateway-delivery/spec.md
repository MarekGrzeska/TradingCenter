## MODIFIED Requirements

### Requirement: Wiadomość jest adresowana nazwą

Wywołujący MUST adresować wiadomość dokładnie jedną z dwóch nazw: nazwą adresata, którą zna z listy,
albo celem, z którego adresata wybiera przypisanie (`telegram-gateway-purposes`). Kontrakt MUST NOT
przyjmować identyfikatora czatu ani nazwy bota od wywołującego. Wiadomość z obiema nazwami albo z
żadną MUST być odmową.

Identyfikator czatu jest liczbą, którą każdy wywołujący musiałby skądś mieć i trzymać u siebie, a
wymiana bota unieważniałaby wszystkie te kopie naraz. Cel idzie krok dalej: producent nie zna nawet
nazwy adresata, więc przepięcie go w terminalu nie dotyka żadnego producenta.

#### Scenario: Nieznany adresat

- **WHEN** wywołujący adresuje wiadomość nazwą adresata, której moduł nie zna
- **THEN** moduł MUST odmówić, wskazując nazwę, i MUST NOT wysłać niczego

#### Scenario: Adresat i cel naraz

- **WHEN** wywołujący podaje w jednej wiadomości i adresata, i cel
- **THEN** moduł MUST odmówić i MUST NOT wysłać niczego

#### Scenario: Wiadomość celem

- **WHEN** wywołujący podaje cel, do którego pasuje przypisanie gotowego adresata
- **THEN** moduł MUST wysłać wiadomość do tego adresata i MUST w odpowiedzi nazwać adresata, do którego trafiła

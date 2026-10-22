## MODIFIED Requirements

### Requirement: Znacznik po udanej wysyłce

Moduł MUST opublikować każdy odczytany film jako zdarzenie „film odczytany” z kluczem źródłowym
równym identyfikatorowi filmu, na podstawie odczytu promptem filmu. Moduł MUST oznaczyć film jako opublikowany
dopiero po odpowiedzi pakietu alertów oznaczającej przyjęcie i MUST NOT publikować ponownie filmu ze znacznikiem.
Nieprzyjęta publikacja MUST zostać ponowiona w kolejnym przebiegu. Film bez odczytu promptem filmu MUST NOT być
publikowany. Odczyt zamówiony innym promptem MUST NOT być publikowany.

#### Scenario: Pakiet alertów odmawia

- **WHEN** pakiet alertów odmawia przyjęcia zdarzenia
- **THEN** film MUST NOT dostać znacznika, a następny przebieg MUST spróbować ponownie

#### Scenario: Film bez odczytu

- **WHEN** film jest przetranskrybowany, a model nie jest skonfigurowany
- **THEN** moduł MUST NOT opublikować o nim niczego

#### Scenario: Film wskazany ręcznie

- **WHEN** film, który wskazał operator albo agent, zostaje odczytany, a jego jedynym źródłem jest wskazanie
- **THEN** moduł MUST NOT go publikować, a film MUST zakończyć jako cichy

#### Scenario: Dodatkowy odczyt innym promptem

- **WHEN** operator zamawia odczyt opublikowanego już filmu innym promptem
- **THEN** moduł MUST NOT publikować niczego

### Requirement: Wiadomość prowadzi do filmu

Moduł MUST ogłosić typ zdarzenia „film odczytany” z atrybutami: kanał, temat (gdy film przyszedł z
tematu), tytuł, ocena wpływu, nazwa promptu, odnośnik do filmu na YouTube oraz gotowa treść powiadomienia.
Zdarzenie MUST NOT nieść instrumentów. Treść MUST nieść tytuł, kanał, krótkie streszczenie, ocenę wpływu i
odnośnik, i MUST mieścić się w limicie długości bramy.

#### Scenario: Długie streszczenie

- **WHEN** streszczenie przekracza miejsce w treści powiadomienia
- **THEN** moduł MUST je skrócić sam, zamiast opublikować treść, której brama odmówi

# youtube-data-alerts Specification

## Purpose
TBD - created by archiving change add-youtube-archive. Update Purpose after archive.
## Requirements
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
Zdarzenie MUST NOT nieść instrumentów. Treść MUST nieść tytuł, kanał, ocenę wpływu, pełny tekst odczytu
promptem filmu i odnośnik, i MUST mieścić się w limicie treści zdarzenia.

#### Scenario: Odczyt z sekcjami

- **WHEN** prompt kanału każe ułożyć odczyt w sekcje, a model tak go napisał
- **THEN** treść powiadomienia MUST nieść ten tekst, a nie streszczenie

#### Scenario: Odczyt dłuższy niż limit zdarzenia

- **WHEN** tekst odczytu przekracza miejsce w treści zdarzenia
- **THEN** moduł MUST go skrócić sam ze znakiem cięcia, a odnośnik do filmu MUST zostać na końcu treści

### Requirement: Brak adresata jest stanem wspieranym

Gdy pakiet alertów nie jest zamontowany w procesie, moduł MUST działać normalnie, MUST NOT publikować
niczego, MUST NOT stawiać znaczników publikacji i MUST mówić w trasie stanu, że nie publikuje.

#### Scenario: Pakiet alertów nieobecny

- **WHEN** film zostaje odczytany, a pakiet alertów nie jest zamontowany
- **THEN** film MUST zostać zapisany normalnie, bez błędu i bez publikacji


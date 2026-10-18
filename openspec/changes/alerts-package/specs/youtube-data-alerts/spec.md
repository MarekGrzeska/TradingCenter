## MODIFIED Requirements

### Requirement: Znacznik po udanej wysyłce

Moduł MUST opublikować każdy odczytany film jako zdarzenie „film odczytany” z kluczem źródłowym
równym identyfikatorowi filmu. Moduł MUST oznaczyć film jako opublikowany dopiero po odpowiedzi
pakietu alertów oznaczającej przyjęcie i MUST NOT publikować ponownie filmu ze znacznikiem.
Nieprzyjęta publikacja MUST zostać ponowiona w kolejnym przebiegu. Film bez odczytu MUST NOT być
publikowany.

#### Scenario: Pakiet alertów odmawia

- **WHEN** pakiet alertów odmawia przyjęcia zdarzenia
- **THEN** film MUST NOT dostać znacznika, a następny przebieg MUST spróbować ponownie

#### Scenario: Film bez odczytu

- **WHEN** film jest przetranskrybowany, a model nie jest skonfigurowany
- **THEN** moduł MUST NOT opublikować o nim niczego

### Requirement: Wiadomość prowadzi do filmu

Moduł MUST ogłosić typ zdarzenia „film odczytany” z atrybutami: kanał, temat (gdy film przyszedł z
tematu), tytuł, ocena wpływu, instrumenty z kierunkiem, odnośnik do filmu na YouTube oraz gotowa
treść powiadomienia. Treść MUST nieść tytuł, kanał, krótkie streszczenie, instrumenty z kierunkiem,
ocenę wpływu i odnośnik, i MUST mieścić się w limicie długości bramy.

#### Scenario: Długie streszczenie

- **WHEN** streszczenie przekracza miejsce w treści powiadomienia
- **THEN** moduł MUST je skrócić sam, zamiast opublikować treść, której brama odmówi

### Requirement: Brak adresata jest stanem wspieranym

Gdy pakiet alertów nie jest zamontowany w procesie, moduł MUST działać normalnie, MUST NOT publikować
niczego, MUST NOT stawiać znaczników publikacji i MUST mówić w trasie stanu, że nie publikuje.

#### Scenario: Pakiet alertów nieobecny

- **WHEN** film zostaje odczytany, a pakiet alertów nie jest zamontowany
- **THEN** film MUST zostać zapisany normalnie, bez błędu i bez publikacji

## REMOVED Requirements

### Requirement: Regułę alertu wybiera kanał i temat
**Reason**: To, czy film jest wart wiadomości, ustala reguła operatora w pakiecie alertów, filtrując po kanale, temacie i ocenie.
**Migration**: Przy pierwszym starcie pakietu alertów kanał albo temat z regułą „zawsze” staje się regułą z filtrem na ten kanał albo temat, a z regułą „od progu” — regułą z dodatkowym filtrem oceny równym dotychczasowemu progowi. Kanały i tematy z regułą „nigdy” nie dostają reguły. Po migracji pole reguły znika z kanałów i tematów.

## MODIFIED Requirements

### Requirement: Post bez odczytu modelu nie powiadamia

Moduł MUST publikować zdarzenie „post odczytany” wyłącznie dla posta, który ma ocenę wpływu. Post bez
oceny — bo model nie jest skonfigurowany albo odczyt się nie udał — MUST NOT być publikowany.

Brak oceny nie jest oceną niską ani wysoką. Opublikowany z oceną zastępczą przeszedłby przez każdy
filtr reguły dokładnie wtedy, gdy moduł wie najmniej.

#### Scenario: Model nieskonfigurowany

- **WHEN** moduł zbiera posty bez skonfigurowanego modelu
- **THEN** MUST NOT opublikować żadnego zdarzenia

### Requirement: Znacznik jest stawiany po udanej wysyłce i jest mechanizmem ponowienia

Moduł MUST ogłosić typ zdarzenia „post odczytany” z atrybutami: autor, ocena wpływu, tematy, adres i
gotowa treść powiadomienia po polsku. Każdy odczytany post MUST zostać opublikowany jako zdarzenie z
kluczem źródłowym równym identyfikatorowi posta. Moduł MUST postawić znacznik „opublikowano” dopiero
po odpowiedzi pakietu alertów oznaczającej przyjęcie i MUST NOT publikować ponownie posta ze
znacznikiem. Nieprzyjęta publikacja MUST zostać ponowiona w następnym przebiegu.

O tym, czy z posta powstanie wiadomość i do kogo trafi, decydują reguły pakietu alertów, nie moduł.

#### Scenario: Pakiet alertów nie przyjął zdarzenia

- **WHEN** publikacja posta kończy się odmową albo brakiem odpowiedzi
- **THEN** moduł MUST NOT postawić znacznika, a następny przebieg MUST spróbować ponownie

#### Scenario: Post już opublikowany

- **WHEN** przebieg zbiórki napotyka post ze znacznikiem
- **THEN** MUST NOT publikować go ponownie

### Requirement: Brak bramy jest stanem wspieranym

Moduł MUST zbierać i wzbogacać normalnie, gdy pakiet alertów nie jest zamontowany w procesie. MUST NOT
odmawiać startu, MUST NOT przerywać zbiórki, MUST NOT stawiać znaczników publikacji i MUST powiedzieć
przez własną trasę stanu, że nie publikuje zdarzeń.

#### Scenario: Pakiet alertów nieobecny

- **WHEN** pakiet alertów nie jest zamontowany, a zbiórka odczytuje post
- **THEN** moduł MUST zapisać post normalnie, MUST NOT postawić znacznika i MUST NOT potraktować tego jako błędu

## REMOVED Requirements

### Requirement: Powiadamia post, który przekroczył próg oceny wpływu
**Reason**: Próg „czy warto” należy do reguły operatora, a nie do ustawienia modułu.
**Migration**: Reguła zdarzenia „post odczytany” z filtrem `impact_score` ≥ próg. Przy pierwszym starcie pakietu alertów przypisania `social` stają się taką regułą z progiem równym dotychczasowemu `ALERT_MIN_IMPACT_SCORE`. Od tej chwili ustawienie przestaje być czytane i trafia na listę `RETIRED_SETTINGS`.

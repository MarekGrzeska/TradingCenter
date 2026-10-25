## MODIFIED Requirements

### Requirement: Powierzchnia narzędzi pakietu strategii

Pakiet MUST publikować narzędzia: `strategy_language` (opis języka), `list_strategies`, `read_strategy`,
`validate_strategy`, `draft_strategy`, `save_strategy`, `run_backtest`, `read_run` i `compare_runs`. Każde narzędzie MUST
używać tej samej logiki co odpowiadająca mu trasa REST, czyli tej samej walidacji i tych samych odmów, a odmowa MUST
wracać do modelu jako wynik z problemami, ich ścieżkami, kolumnami i podpowiedziami. `strategy_language` MUST powstawać
z tego samego rejestru i katalogu co `GET /language`. `read_strategy` MUST podawać dokument wskazanej albo ostatniej
rewizji, jego streszczenie, licznik prób i to, czy instrument ma profil kosztów. `read_run` MUST podawać stan, metryki,
punkty odniesienia i pochodzenie wyniku, ale MUST NOT oddawać modelowi krzywej kapitału ani pełnej listy transakcji.

Serializowana powierzchnia narzędzi pakietu MUST mieścić się w nazwanym suficie znaków.

#### Scenario: Pakiet nieobecny

- **WHEN** proces działa bez `STRATEGIES_DATABASE_URL`
- **THEN** rozmowa MUST NOT dostać żadnego narzędzia strategii, a pozostałe narzędzia MUST działać jak dotąd

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wskaźnik z wyjściem liniowym
- **THEN** `strategy_language` MUST go wymieniać bez zmiany kodu pakietu

### Requirement: Opisy narzędzi prowadzą autora strategii

Opisy narzędzi MUST mówić modelowi, że:
- gdy opis operatora zostawia wartość otwartą, model pyta o nią albo zapisuje przyjęte założenie w `notes`;
- streszczenie zwracane przez zapis, szkic i walidację należy porównać z opisem operatora przed odpowiedzią;
- parametrów nie zmienia się po to, żeby szukać lepszego wyniku;
- każdą zmianę dokumentu kładzie się do edytora szkicem, a rewizję zapisuje się, gdy operator o to prosi;
- nazwę, hipotezę i założenia pisze się po polsku.

#### Scenario: Opis bez godzin sesji

- **WHEN** model czyta opisy narzędzi strategii
- **THEN** opis `save_strategy` MUST mówić, że każde założenie, którego operator nie podał, trafia do `notes`

#### Scenario: Język opisów

- **WHEN** model czyta, jak pisać strategię
- **THEN** MUST przeczytać, że nazwa, hipoteza i założenia są po polsku

## ADDED Requirements

### Requirement: Agent kładzie szkic do edytora bez rewizji

`draft_strategy` MUST sprawdzać dokument tak samo jak walidacja i MUST zapisywać go jako szkic strategii wskazanej przez
identyfikator albo, bez identyfikatora, jako szkic nowej strategii. Szkic MUST zostać zapisany także wtedy, gdy dokument
ma problemy, a odpowiedź MUST nieść wszystkie problemy i, dla poprawnego dokumentu, streszczenie. Szkic MUST NOT tworzyć
rewizji ani zmieniać licznika prób. Każda strategia i nowa strategia MUST mieć co najwyżej jeden szkic: kolejny zastępuje
poprzedni. Zapis rewizji strategii MUST usuwać jej szkic, a utworzenie strategii MUST usuwać szkic nowej.

#### Scenario: Zmiana stopu bez zapisu

- **WHEN** agent kładzie szkic strategii 7 ze zmienionym stopem
- **THEN** szkic strategii 7 MUST nieść ten dokument, a liczba rewizji i prób MUST pozostać bez zmian

#### Scenario: Zapis usuwa szkic

- **WHEN** operator zapisuje rewizję strategii, która ma szkic
- **THEN** szkic MUST zniknąć

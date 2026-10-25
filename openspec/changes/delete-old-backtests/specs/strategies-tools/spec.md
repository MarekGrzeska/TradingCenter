## MODIFIED Requirements

### Requirement: Powierzchnia narzędzi pakietu strategii

Pakiet MUST publikować narzędzia: `strategy_language` (opis języka), `list_strategies`, `read_strategy`,
`validate_strategy`, `draft_strategy`, `save_strategy`, `run_backtest`, `read_backtest`, `compare_runs` i
`delete_backtests`. Każde narzędzie MUST używać tej samej
logiki co odpowiadająca mu trasa REST, czyli tej samej walidacji i tych samych odmów, a odmowa MUST wracać do modelu jako
wynik z problemami, ich ścieżkami, kolumnami i podpowiedziami. `strategy_language` MUST powstawać z tego samego rejestru
i katalogu co `GET /language`. `read_strategy` MUST podawać dokument wskazanej albo ostatniej rewizji, jego streszczenie,
licznik prób i to, czy instrument ma profil kosztów. `read_backtest` MUST podawać stan, metryki, punkty odniesienia i
pochodzenie wyniku, ale MUST NOT oddawać modelowi krzywej kapitału ani pełnej listy transakcji. `read_backtest` i
`compare_runs` MUST odpowiadać na uruchomienie, którego nie ma, odmową, która mówi, że mogło zostać usunięte.

Serializowana powierzchnia narzędzi pakietu MUST mieścić się w nazwanym suficie znaków.

#### Scenario: Pakiet nieobecny

- **WHEN** proces działa bez `STRATEGIES_DATABASE_URL`
- **THEN** rozmowa MUST NOT dostać żadnego narzędzia strategii, a pozostałe narzędzia MUST działać jak dotąd

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wskaźnik z wyjściem liniowym
- **THEN** `strategy_language` MUST go wymieniać bez zmiany kodu pakietu

#### Scenario: Odczyt usuniętego uruchomienia

- **WHEN** agent czyta przez `read_backtest` uruchomienie, które operator usunął
- **THEN** narzędzie MUST odmówić, mówiąc, że uruchomienia nie ma i mogło zostać usunięte

## ADDED Requirements

### Requirement: Agent usuwa uruchomienia na prośbę operatora

`delete_backtests` MUST przyjmować od jednego do dwudziestu różnych identyfikatorów uruchomień i usuwać je według
`strategies-backtest`, z tymi samymi odmowami co `DELETE /runs`. Odpowiedź MUST wymieniać usunięte uruchomienia i
licznik prób strategii, który nie zmalał. Opis narzędzia MUST mówić, że służy do usuwania tylko tych uruchomień, o które
poprosił operator, że usunięcia nie da się cofnąć i że licznik prób zostaje. Narzędzie MUST NOT usuwać uruchomień
czekających ani liczonych, a MUST NOT wybierać uruchomień do usunięcia samo.

#### Scenario: Usunięcie na prośbę

- **WHEN** operator prosi agenta o usunięcie uruchomień 3 i 5, a oba są zakończone
- **THEN** narzędzie MUST usunąć oba i odpowiedzieć ich numerami
- **AND** odczyt strategii MUST nadal pokazywać licznik prób sprzed usunięcia

#### Scenario: Uruchomienie w toku

- **WHEN** agent próbuje usunąć uruchomienie, które się liczy
- **THEN** narzędzie MUST odmówić, nazywając to uruchomienie i jego stan, i MUST NOT usunąć żadnego z podanych

#### Scenario: Za dużo naraz

- **WHEN** agent podaje dwadzieścia jeden identyfikatorów
- **THEN** narzędzie MUST odmówić, nie usuwając żadnego

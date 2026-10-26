## MODIFIED Requirements

### Requirement: Powierzchnia narzędzi pakietu strategii

Pakiet MUST publikować narzędzia: `strategy_language` (opis języka), `list_strategies`, `read_strategy`,
`validate_strategy`, `draft_strategy`, `save_strategy`, `run_backtest`, `read_backtest`, `read_backtest_trades`,
`compare_runs` i `delete_backtests`. Każde narzędzie MUST używać tej samej
logiki co odpowiadająca mu trasa REST, czyli tej samej walidacji i tych samych odmów, a odmowa MUST wracać do modelu jako
wynik z problemami, ich ścieżkami, kolumnami i podpowiedziami. `strategy_language` MUST powstawać z tego samego rejestru
i katalogu co `GET /language`. `read_strategy` MUST podawać dokument wskazanej albo ostatniej rewizji, jego streszczenie,
licznik prób i to, czy instrument ma profil kosztów. `read_backtest` MUST podawać stan, metryki, punkty odniesienia i
pochodzenie wyniku, ale MUST NOT oddawać modelowi krzywej kapitału ani listy transakcji; te czyta `read_backtest_trades`.
`read_backtest` i `compare_runs` MUST odpowiadać na uruchomienie, którego nie ma, odmową, która mówi, że mogło zostać
usunięte.

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

#### Scenario: Odczyt raportu nie niesie transakcji

- **WHEN** agent czyta przez `read_backtest` uruchomienie z czterdziestoma transakcjami
- **THEN** odpowiedź MUST NOT zawierać żadnej transakcji

## ADDED Requirements

### Requirement: Agent czyta transakcje uruchomienia stronami

`read_backtest_trades` MUST przyjmować identyfikator uruchomienia, przesunięcie i liczbę transakcji nie większą niż 100
na odpowiedź, i MUST oddawać razem z nimi łączną liczbę transakcji uruchomienia. Każda transakcja MUST nieść: numer, stronę,
czas i cenę wejścia i wyjścia (czasy w UTC), wielkość, początkowy stop, wynik w R, w procentach kapitału przy wejściu i w
pieniądzu, najgłębszą stratę otwartą, koszty rozbite na składniki, przyczynę wyjścia i oznaczenie rozstrzygnięcia
pesymistycznego, z tymi samymi wartościami pustymi co lista w raporcie. Transakcje MUST być w kolejności numerów.
Uruchomienie, którego nie ma, MUST dawać odmowę mówiącą, że mogło zostać usunięte, a uruchomienie niezakończone MUST
dawać odpowiedź z zerem transakcji i jego stanem. Opis narzędzia MUST mówić, że czasy są w UTC, że odpowiedź jest
stroną i że jej przejście nie liczy się jako próba.

#### Scenario: Pierwsza strona

- **WHEN** agent prosi o transakcje uruchomienia, które ma ich 154, z limitem 100
- **THEN** odpowiedź MUST nieść 100 transakcji o numerach od pierwszego
- **AND** łączną liczbę 154

#### Scenario: Druga strona

- **WHEN** agent prosi o te same transakcje z przesunięciem 100 i limitem 100
- **THEN** odpowiedź MUST nieść pozostałe 54 transakcje

#### Scenario: Limit ponad sufit

- **WHEN** agent prosi o 101 transakcji naraz
- **THEN** narzędzie MUST odmówić, podając sufit

#### Scenario: Transakcja bez stopu

- **WHEN** agent czyta transakcje strategii bez stopu
- **THEN** początkowy stop i wynik w R każdej MUST być puste, a wynik w procentach MUST mieć wartość

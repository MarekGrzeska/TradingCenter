## MODIFIED Requirements

### Requirement: Powierzchnia narzędzi pakietu strategii

Pakiet MUST publikować narzędzia: `strategy_language` (opis języka), `list_strategies`, `read_strategy`,
`validate_strategy`, `draft_strategy`, `save_strategy`, `run_backtest`, `read_backtest`, `compare_runs`,
`delete_backtests` i `strategy_signal`. Każde narzędzie MUST używać tej samej
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

## REMOVED Requirements

### Requirement: Narzędzia strategii dostaje tylko rozmowa

**Reason**: Zespół grający strategię na demo potrzebuje decyzji silnika, a nie własnej interpretacji reguł. Powód reguły —
harmonogram zużywający kolejkę i licznik prób — dotyczy tylko narzędzi zapisujących i uruchamiających.
**Migration**: Zastąpione wymaganiem „Zespoły dostają tylko narzędzia strategii do odczytu”.

## ADDED Requirements

### Requirement: Zespoły dostają tylko narzędzia strategii do odczytu

Wszystkie narzędzia pakietu MUST trafiać do rejestru rozmowy jako funkcje w procesie. Do rejestru zespołów MUST trafiać
wyłącznie `list_strategies`, `read_strategy` i `strategy_signal`; żadne narzędzie, które zapisuje rewizję albo szkic,
uruchamia, porównuje albo usuwa backtest, MUST NOT być dostępne agentowi zespołu. Narzędzia pakietu MUST NOT trafiać do
katalogu narzędzi, z którego czytają reguły alertów, i MUST NOT być serwowane przez sieć pod `/strategies/mcp`. Gdy
pakiet nie jest zamontowany, zespoły MUST NOT dostać żadnego narzędzia strategii.

#### Scenario: Narzędzia dla agenta zespołu

- **WHEN** operator przydziela narzędzia agentowi w zespole
- **THEN** wśród dostępnych narzędzi MUST być `list_strategies`, `read_strategy` i `strategy_signal`
- **AND** MUST NOT być `save_strategy`, `draft_strategy`, `run_backtest`, `read_backtest`, `compare_runs` ani
  `delete_backtests`

#### Scenario: Pakiet nieobecny w zespołach

- **WHEN** proces działa bez `STRATEGIES_DATABASE_URL`
- **THEN** katalog narzędzi zespołów MUST NOT zawierać żadnego narzędzia strategii

### Requirement: Sygnał strategii jest decyzją silnika backtestu

`strategy_signal` MUST przyjmować strategię i numer jej rewizji; rewizja MUST być podana, bo zespół gra tę wersję, którą
operator sprawdził, a nie ostatnio zapisaną. Odpowiedź MUST być wyliczona tym samym silnikiem i z tych samych danych
archiwum co backtest, na oknie kończącym się ostatnią zamkniętą świecą interwału strategii, i MUST podawać:

- moment zamknięcia świecy, z której wynika decyzja, i ile sekund minęło od niego;
- decyzję: wejście (strona, typ zlecenia i jego cena, gdy nie jest rynkowe), wyjście z pozycji, którą silnik trzyma
  (z powodem), trzymanie pozycji (z jej stopem i celem, jeśli są) albo brak działania;
- regułę wielkości z dokumentu (tryb i wartość), bez wielkości w jednostkach — pakiet MUST NOT czytać salda ani
  żadnego stanu konta;
- parametry, z którymi liczono — domyślne dokumentu, bo rewizja grana na koncie to rewizja z jej domyślnymi.

Wywołanie MUST NOT tworzyć uruchomienia, MUST NOT zwiększać licznika prób strategii i MUST NOT zapisywać niczego w bazie.
Strategia lub rewizja, której nie ma, MUST być odmową, która to mówi; luka w archiwum na ostatniej świecy MUST być
odmową nazywającą lukę, a nie decyzją „brak działania”.

#### Scenario: Pierwsza świeca sesji nowojorskiej powyżej EMA

- **WHEN** zespół woła `strategy_signal` po zamknięciu pierwszej świecy M5 sesji nowojorskiej, której zamknięcie jest
  powyżej EMA12, dla strategii wchodzącej w takiej sytuacji na długo
- **THEN** odpowiedź MUST podawać wejście `long` rynkowe i moment zamknięcia tej świecy
- **AND** MUST podawać regułę wielkości `margin_fraction` z jej wartością

#### Scenario: Ta sama decyzja co backtest

- **WHEN** dla tej samej rewizji i tych samych danych zestawić decyzje `strategy_signal` liczone po kolejnych świecach z
  transakcjami backtestu na tym samym odcinku
- **THEN** każde wejście i wyjście backtestu MUST mieć odpowiadającą decyzję sygnału na tej samej świecy

#### Scenario: Sygnał nie jest próbą

- **WHEN** zespół woła `strategy_signal` dowolnie wiele razy
- **THEN** licznik prób strategii i lista jej uruchomień MUST pozostać bez zmian

#### Scenario: Brak świecy w archiwum

- **WHEN** archiwum nie ma ostatniej zamkniętej świecy interwału strategii
- **THEN** narzędzie MUST odmówić, nazywając lukę

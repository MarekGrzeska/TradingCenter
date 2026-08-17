# teams-models Specification

## Purpose
Skąd biorą się modele, którymi pracują agenci: co moduł o nich publikuje, jak model wybiera się
osobno dla każdego agenta i co się dzieje z rewizją wskazującą model, którego już nie ma.
## Requirements
### Requirement: Katalog modeli wystarcza do zbudowania wybieraka

Moduł MUST publikować katalog modeli, którymi dysponuje. Wpis katalogu MUST nieść identyfikator
używany przy wyborze, nazwę do pokazania operatorowi, porządek od najtańszego do najdroższego
oraz stawkę za tokeny wejścia i wyjścia.

Konsument MUST móc zbudować wybierak z samego katalogu. Terminal MUST NOT znać żadnego modelu
z nazwy wpisanej w swój kod: dołożenie kolejnego modelu jest wpisem w konfiguracji modułu, nie
zmianą w terminalu.

#### Scenario: Terminal buduje wybierak przy edycji agenta

- **WHEN** terminal odczytuje katalog modeli
- **THEN** każdy wpis niesie identyfikator, nazwę, porządek kosztu i stawki
- **AND** wybierak powstaje bez ani jednego identyfikatora modelu wpisanego w kod terminala

#### Scenario: Dochodzi kolejny model

- **WHEN** moduł zostaje skonfigurowany z dodatkowym modelem
- **THEN** katalog niesie go po restarcie modułu
- **AND** wybierak oferuje go bez zmiany w terminalu

### Requirement: Model wybiera się osobno dla każdego agenta

Definicja MUST pozwalać wskazać model osobno każdemu agentowi i MUST NOT wymuszać jednego
modelu na cały zespół. Dwaj agenci w jednym zespole MAY pracować różnymi modelami.

To jest jedna z rzeczy, które ten moduł ma dać zmierzyć: rola zbierająca dane i rola ważąca
argumenty nie muszą kosztować tyle samo, a pytanie, gdzie droższy model faktycznie zmienia
wynik, jest pytaniem eksperymentalnym, nie konfiguracyjnym.

#### Scenario: Zespół o mieszanych modelach

- **WHEN** definicja wskazuje jednemu agentowi model tańszy, a drugiemu droższy
- **THEN** każdy z nich jest wołany wskazanym mu modelem
- **AND** ślad przebiegu pokazuje przy każdym agencie model, którym pracował

#### Scenario: Agent bez wskazanego modelu

- **WHEN** definicja nie wskazuje agentowi modelu
- **THEN** zapis definicji MUST zostać odrzucony ze wskazaniem tego agenta

### Requirement: Model spoza katalogu jest odmową, nie podmianą

Wskazanie modelu, którego katalog nie zawiera, MUST być odrzucone z komunikatem nazywającym
model jako przyczynę. Moduł MUST NOT wykonać pracy cichaczem modelem innym niż wskazany:
operator dostałby wynik tańszy lub droższy, niż prosił, i dowiedziałby się o tym z faktury,
a porównanie z wcześniejszym przebiegiem porównywałoby dwie różne rzeczy.

Model wycofany z konfiguracji MUST zniknąć z katalogu, a rewizje wskazujące go MUST pozostać
czytelne wraz ze śladem przebiegów, które się na nich odbyły. Uruchomienie takiej rewizji MUST
być odmową nazywającą model.

#### Scenario: Uruchomienie rewizji na modelu, którego już nie ma

- **WHEN** operator uruchamia rewizję wskazującą agentowi model wycofany z konfiguracji
- **THEN** moduł odmawia uruchomienia, nazywając agenta i model
- **AND** rewizja oraz ślad jej wcześniejszych przebiegów pozostają czytelne

#### Scenario: Model bez skonfigurowanej stawki

- **WHEN** model jest dostępny, ale nie ma skonfigurowanej stawki za tokeny
- **THEN** moduł odmawia startu, wskazując model bez stawki jako przyczynę


# agent-models Specification

## Purpose

Opisuje, skąd konsument wie, jakimi modelami agent dysponuje, jak model zostaje wybrany
dla rozmowy i co się dzieje, gdy wybrany model nie istnieje albo przestał istnieć między
jedną wypowiedzią a drugą.

## Requirements

### Requirement: Katalog modeli wystarcza do zbudowania wybieraka

Moduł MUST publikować katalog modeli, którymi dysponuje. Wpis katalogu MUST nieść
identyfikator używany przy wyborze, nazwę do pokazania operatorowi oraz to, czym modele
różnią się między sobą na tyle, by dało się wybrać świadomie — kolejność od najtańszego do
najdroższego i stawkę za tokeny wejścia i wyjścia.

Konsument MUST móc zbudować wybierak z samego katalogu. Terminal MUST NOT znać żadnego
modelu z nazwy wpisanej w swój kod: dołożenie czwartego modelu jest wpisem w katalogu, nie
zmianą w terminalu.

#### Scenario: Terminal buduje wybierak

- **WHEN** terminal odczytuje katalog modeli
- **THEN** każdy wpis niesie identyfikator, nazwę, porządek kosztu i stawki
- **AND** terminal pokazuje wybierak, nie mając w swoim kodzie ani jednego identyfikatora
  modelu

#### Scenario: Dochodzi czwarty model

- **WHEN** moduł zostaje skonfigurowany z dodatkowym modelem
- **THEN** katalog niesie go po restarcie modułu
- **AND** wybierak w terminalu oferuje go bez zmiany w terminalu

### Requirement: Model jest wyborem sesji, a nie instalacji

Sesja MUST nieść model, którym jest prowadzona, wybrany przez operatora spośród katalogu.
Operator MUST móc zmienić model w trakcie rozmowy; zmiana MUST dotyczyć wypowiedzi
następnych, a wypowiedzi wcześniejsze MUST zachować model, którym powstały — inaczej
rachunek za rozmowę nie daje się rozbić na to, co ją naprawdę kosztowało.

Sesja utworzona bez wskazania modelu MUST dostać model domyślny modułu.

#### Scenario: Zmiana modelu w trakcie rozmowy

- **WHEN** operator zmienia model po kilku wymianach zdań i pisze dalej
- **THEN** kolejna odpowiedź powstaje na nowym modelu
- **AND** wcześniejsze wiadomości nadal wskazują model, którym powstały

#### Scenario: Sesja bez wskazanego modelu

- **WHEN** sesja zostaje utworzona bez wskazania modelu
- **THEN** sesja jest prowadzona modelem domyślnym
- **AND** ten model jest przy niej zapisany tak samo jak wybrany ręcznie

### Requirement: Model spoza katalogu jest odmową, nie podmianą

Żądanie wskazujące model, którego katalog nie zawiera, MUST być odrzucone z komunikatem
nazywającym model jako przyczynę. Moduł MUST NOT wykonać go cichaczem modelem domyślnym:
operator dostałby odpowiedź tańszą lub droższą, niż prosił, i dowiedziałby się o tym z
faktury.

Model wycofany z konfiguracji MUST zniknąć z katalogu, ale sesje prowadzone nim wcześniej
MUST pozostać czytelne — transkrypt i zużycie MUST NOT zależeć od tego, czy model nadal
istnieje.

#### Scenario: Nieznany identyfikator modelu

- **WHEN** przychodzi żądanie z identyfikatorem modelu spoza katalogu
- **THEN** moduł odmawia wykonania
- **AND** komunikat wskazuje model jako przyczynę

#### Scenario: Sesja na modelu, którego już nie ma

- **WHEN** operator otwiera sesję prowadzoną modelem usuniętym z konfiguracji
- **THEN** transkrypt i zużycie tej sesji dają się odczytać
- **AND** dalsza rozmowa wymaga wskazania modelu obecnego w katalogu

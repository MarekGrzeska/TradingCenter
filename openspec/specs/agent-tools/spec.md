# agent-tools Specification

## Purpose

Opisuje narzędzia agenta: skąd bierze się ich zestaw, jak wygląda tura, w której model
po nie sięga, ile razy może to zrobić, co się dzieje z odmową i co po wywołaniu zostaje
zapisane.
## Requirements
### Requirement: Model sięga po narzędzia w trakcie odpowiadania

Moduł MUST pozwalać modelowi poprosić o wywołanie narzędzia w trakcie tury, wykonać je i
oddać wynik modelowi, który mówi dalej. Tura MUST kończyć się wypowiedzią skierowaną do
operatora, nigdy prośbą o narzędzie pozostawioną bez odpowiedzi.

Wypowiedź zapisana w transkrypcie MUST być tym, co model powiedział operatorowi. Prośby
o narzędzia i ich wyniki MUST NOT być wiadomościami w transkrypcie — transkrypt jest
zapisem rozmowy, a nie zapisem tego, jak agent do niej doszedł.

#### Scenario: Pytanie wymagające danych archiwum

- **WHEN** operator pyta o coś, na co model nie umie odpowiedzieć bez danych archiwum
- **THEN** model prosi o narzędzie, dostaje jego wynik i odpowiada z tego, co dostał
- **AND** transkrypt niesie pytanie operatora i jedną wypowiedź agenta

#### Scenario: Pytanie bez potrzeby narzędzia

- **WHEN** operator pyta o coś, na co model odpowiada bez danych archiwum
- **THEN** tura kończy się bez ani jednego wywołania narzędzia

### Requirement: Zestaw narzędzi pochodzi z serwera, nie z tego modułu

Moduł MUST pobierać zestaw dostępnych narzędzi wraz z ich opisami od serwera narzędzi i
MUST NOT nieść własnej listy narzędzi ani własnych opisów **tych, które serwer ogłasza**.
Narzędzie dołożone po stronie serwera MUST stać się dostępne modelowi bez zmiany w tym
module.

Moduł MUST NOT publikować modelowi narzędzia, którego serwer nie ogłosił — **poza
narzędziami wymienionymi z nazwy w specyfikacjach tego modułu**. Dziś jest to jedno
narzędzie: ustawienie zawartości wykresu w terminalu (`agent-chart-control`). Narzędzie
własne modułu MUST być odróżnialne od narzędzia serwera w śladzie wywołania, żeby dało się
powiedzieć, kto je wykonał.

Moduł MUST NOT dokładać narzędzia własnego przez ustawienie ani tryb: granica przebiega
w specyfikacji i jej przesunięcie kosztuje zmianę tego dokumentu.

#### Scenario: Narzędzie dołożone po stronie serwera

- **WHEN** serwer narzędzi zaczyna ogłaszać narzędzie, którego wcześniej nie było
- **THEN** model dostaje je w kolejnej sesji modułu z serwerem, bez zmiany w tym module

#### Scenario: Opis narzędzia zmieniony po stronie serwera

- **WHEN** serwer zmienia opis narzędzia
- **THEN** model widzi opis serwera, a nie kopię trzymaną w tym module

#### Scenario: Narzędzie własne modułu obok narzędzi serwera

- **WHEN** moduł ma połączenie z serwerem narzędzi
- **THEN** model dostaje narzędzia serwera oraz narzędzie ustawiające wykres
- **AND** ślad wywołania mówi, które z nich zostało wykonane przez ten moduł

#### Scenario: Brak serwera narzędzi

- **WHEN** moduł nie ma skonfigurowanego serwera narzędzi
- **THEN** model dostaje samo narzędzie ustawiające wykres, zamiast żadnego

### Requirement: Tura ma sufit wywołań narzędzi

Liczba wywołań narzędzi w jednej turze MUST być ograniczona z góry. Model wpadający w
cykl kosztuje przy każdym obrocie, a operator widzi wyłącznie brak odpowiedzi.

Po osiągnięciu sufitu model MUST dostać to jako informację i MUST mieć możliwość
odpowiedzenia operatorowi. Tura MUST NOT urwać się bez wypowiedzi.

#### Scenario: Model prosi o narzędzia bez końca

- **WHEN** model prosi o kolejne narzędzia po osiągnięciu sufitu tury
- **THEN** kolejne wywołanie nie zostaje wykonane
- **AND** model dostaje informację o sufitcie i odpowiada operatorowi tym, co ma

### Requirement: Odmowa narzędzia jest wynikiem, nie awarią tury

Odmowa pochodząca z serwera narzędzi — nieznany symbol, żądanie ponad sufit, nieznany
wskaźnik — MUST być oddana modelowi jako wynik wywołania, wraz ze zdaniem, którym serwer
ją uzasadnił. Model MUST móc na jej podstawie poprawić żądanie i spróbować ponownie, w
granicach sufitu tury.

Odmowa narzędzia MUST NOT kończyć tury błędem. Poprawialny błąd przedstawiony operatorowi
jako awaria odbiera modelowi jedyną rzecz, po którą to zdanie zostało napisane.

#### Scenario: Model prosi o nieznany symbol

- **WHEN** model woła narzędzie z symbolem, którego archiwum nie zna
- **THEN** odmowa serwera trafia do modelu jako wynik wywołania
- **AND** model może zawołać narzędzie ponownie z poprawionym symbolem

#### Scenario: Model prosi o zakres ponad sufit narzędzia

- **WHEN** serwer odmawia, nazywając parametr do zmiany
- **THEN** to zdanie dociera do modelu
- **AND** tura toczy się dalej

### Requirement: Wywołanie narzędzia zostawia ślad

Każde wykonane wywołanie narzędzia MUST zostawić zapis niosący: sesję i wypowiedź agenta,
w ramach której padło, kolejność w turze, nazwę narzędzia, argumenty, to czy się
powiodło, oraz wynik albo powód odmowy i czas trwania.

Zapis MUST powstać także wtedy, gdy wywołanie zakończyło się odmową, i także wtedy, gdy
tura zakończyła się niepełną odpowiedzią. Wywołanie, które kosztowało czas i pieniądze i
nie zostawiło śladu, jest wywołaniem, o którym nie da się już powiedzieć nic.

Ślad MUST być czytelny dla wołającego, a nie wyłącznie zapisany. Odczyt transkryptu MUST
zwracać wywołania przy wypowiedzi agenta, w ramach której padły, w kolejności, w jakiej
padły. Ślad, po który trzeba sięgnąć zapytaniem do bazy, jest śladem, którego operator nie
ma — a odróżnienie „archiwum nie ma danych" od „narzędzie nie odpowiedziało" jest możliwe
wyłącznie z niego.

Kolejność MUST być odtwarzalna z samej odpowiedzi: dwa wywołania tej samej tury MUST dać
się ustawić względem siebie bez sięgania po ich czas zapisu.

#### Scenario: Tura z kilkoma wywołaniami

- **WHEN** model wywołuje w jednej turze trzy narzędzia
- **THEN** powstają trzy zapisy wskazujące tę samą wypowiedź agenta
- **AND** ich kolejność w turze da się odtworzyć

#### Scenario: Wywołanie zakończone odmową

- **WHEN** wywołanie narzędzia kończy się odmową serwera
- **THEN** zapis powstaje i niesie powód odmowy

#### Scenario: Transkrypt niesie wywołania

- **WHEN** wołający odczytuje transkrypt sesji, w której agent sięgał po narzędzia
- **THEN** przy wypowiedzi agenta przychodzą wywołania, które ją poprzedziły
- **AND** każde niesie nazwę, argumenty, to jak się skończyło, wynik albo powód odmowy
  oraz czas trwania

#### Scenario: Wypowiedź bez narzędzi

- **WHEN** wołający odczytuje wypowiedź, przy której nie padło żadne wywołanie
- **THEN** dostaje pustą listę wywołań, a nie brak pola
- **AND** MUST NOT dać się jej pomylić z wypowiedzią, przy której wywołania odpadły po
  drodze

### Requirement: Agent zapisuje wyłącznie w widoku terminala

Jedyną zmianą stanu, jaką moduł MUST umieć wykonać przez narzędzie, jest ustawienie tego,
co terminal rysuje: zestawu wskaźników, symbolu i interwału aktywnego slotu.

Moduł MUST NOT wykonywać przez narzędzia żadnej innej zmiany stanu: nie rozpoczyna
zbierania pary, nie kasuje danych, nie składa zlecenia, nie zmienia konfiguracji żadnego
modułu i nie pisze do archiwum. Serwer narzędzi MUST pozostać czytający — zapis nie jedzie
przez niego.

Zapis MUST być odwracalny ręką operatora tym samym wybierakiem, którym operator ustawia
wykres sam. Narzędzie, którego skutku operator nie umie cofnąć bez agenta, jest poza tym
wymaganiem.

#### Scenario: Operator prosi o pokazanie wskaźnika

- **WHEN** operator prosi agenta, żeby pokazał EMA 200 na wykresie
- **THEN** agent ma narzędzie, którym to robi, i wykres to pokazuje

#### Scenario: Operator prosi o wykonanie akcji poza wykresem

- **WHEN** operator prosi agenta, żeby zaczął zbierać parę albo złożył zlecenie
- **THEN** agent nie ma narzędzia, którym mógłby to zrobić
- **AND** odpowiada, że to jest poza jego zakresem, zamiast zgłaszać chwilową awarię

#### Scenario: Operator cofa to, co ustawił agent

- **WHEN** operator usuwa wybierakiem wskaźnik, który ustawił agent
- **THEN** wskaźnik znika i nie wraca sam z siebie


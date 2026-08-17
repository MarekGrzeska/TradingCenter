# agent-trading Specification

## Purpose

Na jakich warunkach rozmowa rusza rachunek: czego ten moduł nie narzuca, co zostaje w
śladzie po każdym wywołaniu zmieniającym stan rachunku, i czego agent nie ma prawa
operatorowi powiedzieć o zleceniu, którego skutku nie zna.
## Requirements
### Requirement: Moduł nie narzuca własnych granic handlowych

Moduł MUST NOT nieść własnej granicy wielkości zlecenia, liczby zleceń w turze, w rozmowie
ani dobowo. MUST NOT podstawiać żadnej wartości domyślnej i MUST NOT trzymać w kodzie
sufitu, którego operator nie może podnieść. Wywołanie zapisujące MUST NOT być odmówione
wyłącznie z powodu granicy pochodzącej z tego modułu, bo takiej granicy tu nie ma.

To jest ten sam wybór, jaki `teams` zrobił dla swoich zespołów (`teams-trading`, „Granice
są narzędziem operatora, nie zgodą, której moduł mu udziela"), tylko bez miejsca, w którym
operator mógłby je zapisać: rozmowa nie ma rewizji, więc granica trzymana tutaj byłaby
jedną liczbą dla wszystkich rozmów i nie byłoby jej w śladzie. Ochroną przed nieodwracalnym
skutkiem jest rachunek demonstracyjny wymuszony u gatewaya, a nie liczba, której operator
nie może zmienić.

Sufit wywołań narzędzi w turze (`agent-tools`, „Tura ma sufit wywołań narzędzi") MUST
obowiązywać dalej i MUST NOT być przedstawiany jako granica handlowa. Jest tam po to, żeby
model wpadający w cykl przestał kosztować, a nie po to, żeby zliczać zlecenia — komunikat o
jego osiągnięciu MUST NOT nazywać przyczyny granicą handlową.

#### Scenario: Operator prosi o zlecenie dowolnie dużej wielkości

- **WHEN** operator prosi agenta o zlecenie o wielkości, jakiej ten moduł nie uznałby za
  rozsądną
- **THEN** moduł wysyła je bez zmiany wielkości
- **AND** odmowa, jeśli padnie, MUST pochodzić od serwera narzędzi albo od providera, a nie
  z granicy tego modułu

#### Scenario: Wiele zleceń w jednej rozmowie

- **WHEN** w jednej rozmowie pada więcej wywołań zapisujących, niż moduł uznałby za
  rozsądne
- **THEN** żadne z nich nie zostaje odmówione z powodu ich liczby

#### Scenario: Tura osiąga sufit wywołań przy narzędziu zapisującym

- **WHEN** tura osiąga sufit wywołań narzędzi, a ostatnie z nich było zapisujące
- **THEN** model dostaje informację o sufitcie tury i odpowiada operatorowi
- **AND** informacja MUST NOT czytać się jak wyczerpana granica handlowa

### Requirement: Wywołanie ruszające rachunek zostawia ślad przed wysłaniem

Ślad wywołania zmieniającego stan rachunku MUST powstać **przed** wysłaniem wywołania do
serwera narzędzi i MUST zostać uzupełniony o skutek, gdy ten wróci. MUST NOT powstawać
dopiero po zakończeniu tury.

Ślad MUST przetrwać turę, która nie zakończyła się wypowiedzią agenta: jego istnienie
MUST NOT zależeć od tego, czy wypowiedź, w ramach której padło wywołanie, powstała.

Wywołanie, którego skutek pozostał nieznany — awaria dostępu, przekroczenie czasu, śmierć
procesu w trakcie — MUST zostać zapisane jako nieznany. MUST NOT zostać zapisane jako
nieudane i MUST NOT zostać usunięte. To jest jedyny ślad zlecenia, które mogło zostać
złożone mimo braku odpowiedzi, i różnica między „nie doszło" a „nie wiadomo" jest tu
różnicą między rachunkiem, na którym nic nie stoi, a rachunkiem, na którym stoi pozycja, o
której nikt nie wie.

Wywołania wyłącznie czytające MAY zostawiać ślad tak, jak zostawiały go dotąd
(`agent-tools`, „Wywołanie narzędzia zostawia ślad"): odczyt, który przepadł, nie zostawia
po sobie niczego na rachunku.

#### Scenario: Tura umiera po złożeniu zlecenia

- **WHEN** proces przerywa turę po wysłaniu wywołania zapisującego, a przed powstaniem
  wypowiedzi agenta
- **THEN** ślad tego wywołania istnieje
- **AND** niesie skutek oznaczony jako nieznany

#### Scenario: Odpowiedź na wywołanie zapisujące nie wraca

- **WHEN** wywołanie zapisujące kończy się awarią dostępu bez znanego skutku
- **THEN** ślad pozostaje ze skutkiem oznaczonym jako nieznany
- **AND** MUST NOT zostać oznaczony jako nieudany

#### Scenario: Zlecenie zostaje złożone

- **WHEN** wywołanie zapisujące dochodzi do skutku
- **THEN** ślad powstały przed wysłaniem zostaje uzupełniony o skutek, jaki wrócił

#### Scenario: Operator odczytuje, co agent zrobił na rachunku

- **WHEN** operator odczytuje transkrypt rozmowy, w której agent sięgał po narzędzia
  zapisujące
- **THEN** widzi te wywołania wraz z ich skutkami, w tym oznaczone jako nieznane

### Requirement: Agent nie potwierdza zlecenia, którego skutku nie zna

Agent MUST NOT stwierdzić, że zlecenie zostało złożone, pozycja zamknięta ani poziom
zmieniony, gdy skutek wywołania jest nieznany. MUST powiedzieć, że skutek jest nieznany, i
MUST nazwać czynność, którą operator sprawdzi stan rachunku samodzielnie.

MUST NOT powtórzyć wywołania zapisującego z własnej inicjatywy po nieznanym skutku. Ponowne
złożenie zlecenia, które mogło już zostać złożone, jest drugą pozycją, a nie ponowną próbą
tej samej.

Skutek nieznany MUST być odróżnialny dla modelu od odmowy narzędzia (`agent-tools`,
„Odmowa narzędzia jest wynikiem, nie awarią tury"). Odmowa mówi „zapytano i odpowiedziano,
że tak nie można", i po niej model MAY poprawić żądanie; nieznany skutek mówi „nie wiadomo,
co się stało", i po nim MUST NOT.

#### Scenario: Agent po nieznanym skutku zlecenia

- **WHEN** wywołanie składające zlecenie kończy się nieznanym skutkiem
- **THEN** agent mówi operatorowi, że nie wie, czy zlecenie zostało złożone
- **AND** MUST NOT stwierdzić, że zostało, ani że nie zostało

#### Scenario: Agent nie ponawia zlecenia sam

- **WHEN** wywołanie składające zlecenie kończy się nieznanym skutkiem, a tura ma jeszcze
  wywołania do sufitu
- **THEN** agent nie wysyła tego wywołania po raz drugi z własnej inicjatywy

#### Scenario: Narzędzie odmawia zlecenia

- **WHEN** serwer narzędzi odmawia wywołania zapisującego, nazywając parametr do zmiany
- **THEN** model dostaje tę odmowę jako wynik i MAY poprawić żądanie
- **AND** odmowa MUST NOT zostać przedstawiona operatorowi jako nieznany skutek

## ADDED Requirements

### Requirement: Wpis dociągnięcia da się usunąć z zakładki

Zakładka MUST pozwalać usunąć z historii wpis dociągnięcia, żeby lista dawała się
uporządkować bez zdejmowania instrumentu i bez kasowania jego danych.

Usunięcie obejmuje całe zlecenie — wszystkie jego pary, każdy kawałek — więc MUST być
wywoływane z dialogu zlecenia, a nie z wiersza pojedynczej pary, dokładnie z tego powodu,
z którego stoi tam ponowienie: przycisk przy wierszu jednej pary obiecuje usunięcie tej
pary, a wykonałby co innego.

Zanim cokolwiek zniknie, zakładka MUST powiedzieć, ilu par i ilu kawałków dotyczy
usunięcie, oraz MUST stwierdzić wprost, że zebrane świece zostają w archiwum. Bez tego
zdania operator ma przed sobą dwie nieodwracalne operacje o nierozróżnialnych nazwach —
skasowanie danych pary i usunięcie wpisu o dociągnięciu.

Po usunięciu zakładka MUST przestać pokazywać wiersze tego zlecenia, bez odświeżania
strony przez operatora. Usunięcie MUST NOT zostawiać po sobie wpisu w historii — wpis
o skasowaniu danych mówi, że ubyło świec, a tu nie ubyło żadnej, i lista rosłaby wtedy
tak samo jak przed tą możliwością.

Zlecenia, którego archiwum nie pozwala usunąć, bo coś się w nim jeszcze dzieje, zakładka
MUST NOT pokazywać jako usuwalnego.

#### Scenario: Operator usuwa zlecenie

- **WHEN** operator wybiera usunięcie w dialogu zlecenia i je potwierdza
- **THEN** wiersze tego zlecenia znikają z zakładki bez odświeżania strony
- **AND** wiersze pozostałych zleceń i wpisy o skasowaniach danych zostają na miejscu

#### Scenario: Potwierdzenie nazywa skutek

- **WHEN** operator wybiera usunięcie w dialogu zlecenia
- **THEN** przed usunięciem widzi, ilu par i ilu kawałków ono dotyczy
- **AND** widzi stwierdzenie, że zebrane świece pozostają w archiwum

#### Scenario: Usunięcie stoi przy całości, nie przy parze

- **WHEN** operator patrzy na wiersz pary należącej do zlecenia
- **THEN** przy tym wierszu MUST NOT stać przycisk usuwający zlecenie z historii
- **AND** droga do usunięcia prowadzi przez dialog zlecenia

#### Scenario: Zlecenie w toku

- **WHEN** operator otwiera dialog zlecenia, którego kawałki jeszcze się wykonują
- **THEN** usunięcie nie jest dostępne, a dialog mówi, dlaczego
- **AND** ponowienie i pozostała treść dialogu działają jak dotąd

#### Scenario: Usunięcie zawodzi

- **WHEN** żądanie usunięcia nie dochodzi do archiwum
- **THEN** dialog zlecenia mówi, że usunięcie się nie udało, i zostawia możliwość spróbowania raz jeszcze
- **AND** wiersze tego zlecenia pozostają w zakładce

#### Scenario: Wpis o skasowaniu danych

- **WHEN** operator patrzy na wpis o skasowaniu danych pary
- **THEN** nie prowadzi z niego żadna droga do usunięcia wpisu historii

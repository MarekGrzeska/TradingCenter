## Purpose

Źródło „zdarzenie”: coś, co stało się w innym pakiecie procesu, ogłoszone z opisem swoich atrybutów i
opublikowane tak, żeby reguła mogła je przefiltrować bez znajomości kodu producenta.

## ADDED Requirements

### Requirement: Typ zdarzenia jest ogłaszany ze schematem atrybutów

Pakiet MUST ogłosić typ zdarzenia, zanim opublikuje pierwsze zdarzenie tego typu. Ogłoszenie MUST
nieść nazwę kropkowaną, opis po polsku i JSON Schema atrybutów. Ponowne ogłoszenie typu MUST
zastąpić opis i schemat. Reguły, które przestały pasować do nowego schematu, MUST być oznaczone na
liście reguł z nazwą pola i MUST NOT być usuwane.

#### Scenario: Producent ogłasza typ przy starcie

- **WHEN** archiwum YouTube startuje i ogłasza typ `youtube.film.read`
- **THEN** typ MUST być w katalogu z opisem i atrybutami, zanim przyjdzie pierwszy film

#### Scenario: Schemat traci atrybut użyty w regule

- **WHEN** typ zostaje ogłoszony ponownie bez atrybutu, po którym filtruje istniejąca reguła
- **THEN** reguła MUST zostać na liście z oznaczeniem nazywającym brakujący atrybut

### Requirement: Zdarzenie publikuje się tylko z wnętrza procesu

Publikacja i ogłoszenie typu MUST być przyjmowane wyłącznie od pakietów tego samego procesu. Żądanie
z zewnątrz — z terminala, z tokenem operatora albo z kluczem wspólnym — MUST być odmową.

Zdarzenie przyjęte z internetu to wiadomość na telefon operatora, którą napisał ktoś obcy.

#### Scenario: Publikacja z tokenem terminala

- **WHEN** żądanie publikacji zdarzenia przychodzi z ważnym tokenem terminala przez krawędź
- **THEN** pakiet MUST odmówić i MUST NOT zapisać zdarzenia

### Requirement: Zdarzenie jest sprawdzane wobec schematu i idempotentne

Zdarzenie nieznanego typu albo z atrybutami niezgodnymi ze schematem MUST być odmową nazywającą
przyczynę. Zdarzenie MUST nieść klucz źródłowy nadany przez producenta. Ponowna publikacja z tym
samym typem i kluczem MUST zostać przyjęta jako sukces i MUST NOT dać drugiego odpalenia żadnej
reguły.

Producent ponawia publikację, dopóki nie dostanie sukcesu. Bez idempotencji każde ponowienie po
zgubionej odpowiedzi kończyłoby się drugim alertem.

#### Scenario: Ta sama publikacja dwa razy

- **WHEN** producent publikuje zdarzenie, nie dostaje odpowiedzi i publikuje je ponownie z tym samym kluczem
- **THEN** obie publikacje MUST dostać sukces, a reguła MUST odpalić co najwyżej raz

#### Scenario: Atrybut o złym typie

- **WHEN** zdarzenie niesie ocenę wpływu jako tekst, a schemat mówi o liczbie
- **THEN** publikacja MUST być odmową nazywającą ten atrybut

### Requirement: Filtr reguły działa na atrybutach

Filtr reguły zdarzenia MUST być koniunkcją porównań atrybutów ze schematu typu: równość i przynależność
do listy dla tekstu, porównania liczbowe dla liczb, zawieranie dla list. Reguła bez porównań MUST
pasować do każdego zdarzenia swojego typu.

#### Scenario: Film jednego kanału z oceną od 7

- **WHEN** reguła filtruje `channel` równe kanałowi X i `impact_score` nie mniejsze niż 7, a przychodzi film kanału X z oceną 6
- **THEN** reguła MUST NOT odpalić

### Requirement: Zdarzenia mają skończoną retencję

Pakiet MUST usuwać zdarzenia starsze niż okres retencji z ustawień. Usunięcie zdarzenia MUST NOT
usuwać zapisu odpalenia, które z niego powstało.

#### Scenario: Zdarzenie po okresie retencji

- **WHEN** zdarzenie jest starsze niż okres retencji
- **THEN** MUST zostać usunięte, a historia odpaleń MUST dalej pokazywać odpalenie z jego czasem i treścią wysłaną

# agent-prompt-management Specification

## Purpose

Trwały, wersjonowany magazyn promptu systemowego agenta i API do jego odczytu oraz
nadpisania, tak że treść używana w rozmowach nie jest już zaszyta wyłącznie w kodzie
modułu.
## Requirements
### Requirement: Odczyt aktualnego promptu

API MUST publikować aktualną treść obu wariantów promptu (z narzędziami i bez), ich
wspólną wersję i moment ostatniej zmiany.

#### Scenario: Odczyt bez wcześniejszej edycji przez API

- **WHEN** nikt jeszcze nie edytował promptu przez API po wdrożeniu tej zmiany
- **THEN** odczyt zwraca treść zasianą przy migracji i wersję "v4"

#### Scenario: Odczyt po edycji

- **WHEN** operator wcześniej zapisał nową treść
- **THEN** odczyt zwraca dokładnie tę treść i jej wersję

### Requirement: Zapis tworzy nową wersję, nigdy nie nadpisuje istniejącej

Zapis nowej treści MUST utworzyć nową wersję. Zapis MUST NOT nadpisać treść przypisaną
do wersji, która już istnieje — historia poprzednich wersji MUST pozostać czytelna dla
modułu, nawet jeśli dziś nic jej nie odczytuje wprost. Zapis MUST przyjmować oba warianty
naraz i MUST NOT zaakceptować pustego tekstu w którymkolwiek z nich.

#### Scenario: Zapis nowej treści

- **WHEN** operator zapisuje zmienioną treść jednego lub obu wariantów
- **THEN** API tworzy nowy wiersz wersji z podaną treścią i zwraca jej numer
- **AND** poprzedni wiersz wersji pozostaje w magazynie niezmieniony

#### Scenario: Pusty tekst odrzucony

- **WHEN** zapisywany tekst dowolnego wariantu jest pusty
- **THEN** API odrzuca zapis i nie tworzy nowej wersji

### Requirement: Odpowiedź niesie wersję, pod jaką faktycznie padła

Każda odpowiedź agenta MUST być oznaczona wersją promptu aktualną w chwili tej
odpowiedzi. Zmiana promptu po fakcie MUST NOT zmieniać wersji już zapisanej na
istniejących wiadomościach.

#### Scenario: Edycja w trakcie trwania rozmowy

- **WHEN** operator edytuje prompt pomiędzy dwiema turami tej samej rozmowy
- **THEN** pierwsza tura pozostaje oznaczona wersją sprzed edycji
- **AND** druga tura jest oznaczona nową wersją

### Requirement: Zasiew z wdrożenia nie przykrywa tego, co zapisał operator

Treść promptu wstawiana przez migrację jest wartością domyślną, a nie decyzją. Moduł MUST
odróżniać wiersz wstawiony przez migrację od wiersza zapisanego przez operatora i MUST NOT
pozwolić, by zasiew stał się treścią obowiązującą, gdy operator zapisał cokolwiek po
poprzednim zasiewie.

Wersje MUST być unikatowe. Dwa wiersze o tej samej wersji sprawiają, że odczyt zwraca inną
treść, niż mówi jej numer, a usunięcie zasiewu przy wycofaniu migracji zabiera ze sobą
tekst, którego migracja nigdy nie zapisała.

#### Scenario: Wdrożenie zasiewa prompt, gdy operator nic nie zapisał

- **WHEN** migracja zasiewa nową treść promptu, a najnowszy zapis pochodzi z poprzedniego
  zasiewu
- **THEN** nowa treść zostaje zapisana i staje się obowiązująca

#### Scenario: Wdrożenie zasiewa prompt po zapisie operatora

- **WHEN** migracja zasiewa nową treść promptu, a operator zapisał własną treść po
  poprzednim zasiewie
- **THEN** zasiew nie zostaje zapisany
- **AND** odczyt nadal zwraca treść zapisaną przez operatora

#### Scenario: Dwa zapisy o tej samej wersji

- **WHEN** zapisywana jest treść pod wersją, która już istnieje
- **THEN** magazyn odrzuca zapis, zamiast przyjąć drugi wiersz o tej samej wersji


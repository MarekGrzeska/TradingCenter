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

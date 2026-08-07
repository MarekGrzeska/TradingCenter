## Purpose

Miejsce w terminalu, z którego operator decyduje, co archiwum zbiera — dokłada i zdejmuje pary
symbolu z rozdzielczością — oraz widzi, czy to zbieranie faktycznie działa i jak daleko sięga.

## ADDED Requirements

### Requirement: Panel jest zakładką terminala

Zarządzanie archiwizowanymi parami MUST być dostępne jako zakładka terminala, adresowalna własną
ścieżką i wpisana do rejestru zakładek na tych samych zasadach co pozostałe.

#### Scenario: Operator otwiera panel

- **WHEN** operator wchodzi na ścieżkę panelu
- **THEN** widzi listę par aktualnie archiwizowanych

#### Scenario: Odświeżenie strony

- **WHEN** operator odświeża stronę na ścieżce panelu
- **THEN** wraca do panelu, a nie do widoku domyślnego

### Requirement: Operator dokłada parę wybierając instrument i rozdzielczość

Panel MUST pozwalać wskazać instrument oraz rozdzielczość i dodać tę parę do archiwizowanych.
Instrumenty MUST pochodzić z wyszukiwarki, żeby operator nie wpisywał symbolu z pamięci.

#### Scenario: Dodanie pary

- **WHEN** operator wybiera instrument i rozdzielczość, po czym zatwierdza
- **THEN** para pojawia się na liście archiwizowanych
- **AND** panel pokazuje, że zbieranie zostało rozpoczęte

#### Scenario: Para już archiwizowana

- **WHEN** operator dodaje parę, która jest już archiwizowana
- **THEN** panel stwierdza, że taka para już istnieje, i nie tworzy duplikatu

#### Scenario: Archiwum odmawia dodania

- **WHEN** archiwum odmawia dodania pary, na przykład z powodu osiągniętego limitu
- **THEN** panel pokazuje powód odmowy operatorowi

### Requirement: Panel pokazuje, czy zbieranie działa

Sama obecność pary na liście nie dowodzi, że dane przychodzą. Panel MUST pokazywać dla każdej pary
stan zbierania oraz to, jak świeże są dane, żeby cicha awaria ingestu była widoczna bez zaglądania
do logów.

#### Scenario: Przegląd listy

- **WHEN** operator patrzy na listę archiwizowanych par
- **THEN** dla każdej widzi stan zbierania oraz czas najnowszej zebranej świecy

#### Scenario: Zbieranie ustało

- **WHEN** archiwum zgłasza dla pary, że zbieranie nie nadąża albo ustało
- **THEN** panel wyróżnia tę parę spośród pozostałych

### Requirement: Panel pokazuje zasięg archiwum

Operator MUST widzieć, jaki przedział czasu archiwum pokrywa dla danej pary, żeby wiedzieć, na czym
może oprzeć wykres albo backtest.

#### Scenario: Podgląd pokrycia pary

- **WHEN** operator wybiera parę z listy
- **THEN** widzi najstarszy i najnowszy pokryty znacznik czasu
- **AND** informację, czy najstarsza granica wynika z końca historii u providera

### Requirement: Zdjęcie pary jest jawną decyzją

Panel MUST pozwalać przestać archiwizować parę i MUST wymagać potwierdzenia, a przy nim stwierdzić,
że zebrane świece pozostają w archiwum.

#### Scenario: Operator zdejmuje parę

- **WHEN** operator wybiera zaprzestanie archiwizowania pary
- **THEN** panel prosi o potwierdzenie i stwierdza, że dane pozostaną zachowane
- **AND** po potwierdzeniu para znika z listy archiwizowanych

### Requirement: Panel mówi, gdy archiwum nie odpowiada

Panel MUST odróżnić „nie ma żadnych archiwizowanych par" od „nie udało się o nie zapytać".

#### Scenario: Archiwum nieosiągalne

- **WHEN** panel nie może pobrać listy par
- **THEN** pokazuje, że archiwum jest nieosiągalne, zamiast pustej listy

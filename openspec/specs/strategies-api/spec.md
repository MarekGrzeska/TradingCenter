# strategies-api Specification

## Purpose
Kontrakt REST pakietu strategii, kto może go wołać i czego pakiet nie robi: jest narzędziem badawczym bez
żadnej drogi do rachunku.
## Requirements
### Requirement: Kontrakt REST pakietu

Pakiet MUST publikować pod `/strategies` trasy: `GET /language` (opis języka), `POST /validate` (walidacja
bez zapisu), `GET` i `POST /strategies` (lista z licznikiem prób i utworzenie), `GET /strategies/{id}`,
`POST /strategies/{id}/revisions`, `GET /strategies/{id}/revisions/{n}`, `POST /strategies/{id}/archive` i
`/restore`, `POST /runs` (zakolejkowanie), `GET /runs` (lista, z filtrem strategii), `GET /runs/{id}` (stan i
raport), `GET /runs/{id}/trades` (transakcje stronami), `POST /runs/{id}/cancel` oraz `GET /health` (baza,
długość kolejki, uruchomienie w toku). Odmowa MUST nazywać swoją przyczynę i MUST NOT zdradzać błędu bazy.

#### Scenario: Zakolejkowanie uruchomienia

- **WHEN** operator wysyła `POST /runs` z rewizją, zakresem, parametrami i modelem kosztów
- **THEN** odpowiedź MUST przyjść od razu z identyfikatorem uruchomienia w stanie zakolejkowanym

### Requirement: Opis języka z tego samego źródła co walidacja

`GET /language` MUST opisywać sekcje dokumentu, dozwolone konstrukcje, funkcje własne z sygnaturami oraz
wskaźniki katalogu dostępne w danej chwili, i MUST powstawać z tego samego rejestru, z którego korzysta
walidacja. Funkcja, którą walidacja przyjmuje, MUST być w opisie, a funkcja z opisu MUST przechodzić walidację.

#### Scenario: Nowy wskaźnik w katalogu

- **WHEN** do katalogu archiwum dochodzi wpis z wyjściem liniowym
- **THEN** `GET /language` MUST go wymieniać bez zmiany kodu pakietu strategii

### Requirement: Walidacja bez zapisu

`POST /validate` MUST zwracać dokładnie te błędy, które zwróciłby zapis tego samego dokumentu, i MUST NOT niczego
zapisywać ani liczyć jako próby.

#### Scenario: Dokument z błędami

- **WHEN** dokument z dwoma błędami trafia do `POST /validate`
- **THEN** odpowiedź MUST zawierać oba błędy
- **AND** liczba strategii i rewizji w bazie MUST pozostać bez zmian

### Requirement: Dostęp ma operator, nie oglądający

Trasy pakietu MUST przyjmować wołających wyłącznie z listy aplikacji pakietu i, na serwerze, wyłącznie osoby z
rolą `admin`. Osoba z rolą `viewer` MUST dostać odmowę na każdej trasie pakietu, także na odczycie.

#### Scenario: Oglądający czyta listę strategii

- **WHEN** osoba z rolą `viewer` wysyła `GET /strategies/strategies`
- **THEN** odpowiedź MUST być odmową

### Requirement: Pakiet nie ma drogi do rachunku

Pakiet MUST NOT mieć klienta, adresu ani ustawienia prowadzącego do `trading-mcp` albo do bramy capital.com i
MUST NOT publikować decyzji, zdarzeń ani powiadomień. Żadna trasa pakietu MUST NOT składać, zmieniać ani anulować
zlecenia.

#### Scenario: Przegląd zależności pakietu

- **WHEN** test odczytuje importy i ustawienia pakietu strategii
- **THEN** MUST NOT znaleźć importu klienta bramy ani `trading-mcp`, ani ustawienia z ich adresem


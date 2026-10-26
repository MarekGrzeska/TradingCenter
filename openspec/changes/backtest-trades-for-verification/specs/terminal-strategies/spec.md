## ADDED Requirements

### Requirement: Pobranie transakcji uruchomienia jako CSV

Raport uruchomienia MUST oferować „Pobierz transakcje (CSV)”, które zapisuje na dysku operatora plik ze wszystkimi
transakcjami uruchomienia, a nie tylko ze stroną widoczną w tabeli. Nazwa pliku MUST zawierać numer uruchomienia. Gdy
pobranie się nie uda, raport MUST pokazać przyczynę słowami. Pobranie MUST nie zmieniać strony tabeli ani wyboru
transakcji.

#### Scenario: Pobranie przy stronicowanej tabeli

- **WHEN** operator ogląda drugą stronę transakcji uruchomienia o 450 transakcjach i wybiera „Pobierz transakcje (CSV)”
- **THEN** zapisany plik MUST zawierać wszystkie 450
- **AND** tabela MUST nadal pokazywać drugą stronę

#### Scenario: Nieudane pobranie

- **WHEN** pakiet odpowiada na pobranie błędem
- **THEN** raport MUST pokazać, że pobranie się nie udało, a tabela MUST pozostać nietknięta

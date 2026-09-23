## ADDED Requirements

### Requirement: Każda aplikacja jest sprawdzana z zewnątrz

Każda aplikacja App Service systemu MUST mieć test dostępności wykonywany spoza Azure, na ścieżce
wyłączonej z uwierzytelniania, która niczego nie czyta, oraz alert do operatora, gdy test zawodzi.
Metryki platformy MUST NOT być jedynym sygnałem: proces bezczynny i proces martwy raportują tak samo
zero żądań.

#### Scenario: Brama przestaje odpowiadać

- **WHEN** kontener `capital-gateway` nie odpowiada na `/`
- **THEN** operator dostaje alert z testu dostępności tej aplikacji
- **AND** nie musi czekać, aż alert wieku świec zgadnie przyczynę

#### Scenario: Nowa aplikacja na planie

- **WHEN** do planu dochodzi aplikacja App Service
- **THEN** MUST ona dostać swój test dostępności w tej samej zmianie, która ją dodaje

### Requirement: Baza nie ma stałej reguły dla adresu człowieka

Zapora serwera PostgreSQL MUST wpuszczać na stałe tylko adresy wychodzące aplikacji. Dostęp operatora
MUST być regułą tymczasową na bieżący adres, usuwaną w tej samej sesji, w której powstała.

#### Scenario: Operator musi uruchomić skrypt na produkcji

- **WHEN** operator uruchamia `scripts/grant-schema-ownership.sql` albo odczyt statystyk
- **THEN** zakłada regułę na swój bieżący adres przed połączeniem
- **AND** usuwa ją, zanim sesja się skończy, także gdy skrypt się nie powiódł

### Requirement: Obciążenie bazy daje się przypisać do zapytań

Serwer MUST dopuszczać rozszerzenie `pg_stat_statements`, żeby przegląd mógł przypisać obciążenie do
zapytań, a nie tylko do tabel.

#### Scenario: Przegląd pyta, co obciąża bazę

- **WHEN** przegląd systemu odczytuje statystyki produkcji
- **THEN** widzi najdroższe zapytania z liczbą wywołań i czasem

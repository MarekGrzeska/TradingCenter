## MODIFIED Requirements

### Requirement: Każda aplikacja jest sprawdzana z zewnątrz

Każda aplikacja systemu MUST mieć test dostępności wykonywany spoza serwera, na którym działa, na
ścieżce wyłączonej z uwierzytelniania, która niczego nie czyta, oraz alert do operatora, gdy test
zawodzi. Metryki serwera MUST NOT być jedynym sygnałem: proces bezczynny i proces martwy raportują tak
samo zero żądań.

#### Scenario: Brama przestaje odpowiadać

- **WHEN** kontener `capital-gateway` nie odpowiada na swojej trasie zdrowia
- **THEN** operator dostaje alert z testu dostępności tej aplikacji

#### Scenario: Nowa aplikacja na serwerze

- **WHEN** na serwerze dochodzi aplikacja
- **THEN** MUST ona dostać swój test dostępności w tej samej zmianie, która ją dodaje

### Requirement: Baza nie ma stałej reguły dla adresu człowieka

Baza MUST NOT mieć portu osiągalnego spoza serwera. Dostęp operatora MUST odbywać się tunelem SSH
zestawianym na czas sesji, a nie regułą zapory ani publikacją portu.

#### Scenario: Operator musi uruchomić zapytanie na produkcji

- **WHEN** operator potrzebuje połączenia z bazą produkcji
- **THEN** zestawia tunel SSH na czas sesji
- **AND** port bazy pozostaje nieosiągalny z internetu przed, w trakcie i po sesji

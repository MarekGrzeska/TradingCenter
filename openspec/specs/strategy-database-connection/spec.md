# strategy-database-connection Specification

## Purpose
Warunki, na jakich platforma strategii łączy się ze swoją bazą: ta sama reguła, którą mają
pozostałe schematy — tożsamość albo pętla zwrotna, własna baza, własne migracje pod blokadą.
## Requirements
### Requirement: Tożsamość albo pętla zwrotna, nigdy oba i nigdy żadne

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem swojej tożsamości,
odnawialnym w trakcie pracy; adres niosący własne poświadczenie obok skonfigurowanej
tożsamości MUST być odrzucony przy starcie. Bez skonfigurowanej tożsamości moduł MUST NOT
nawiązać połączenia z hostem innym niż pętla zwrotna i MUST odmówić startu z taką
konfiguracją. Połączenie z hostem zdalnym MUST wymuszać szyfrowanie; konfiguracja, która
go nie wymusza, MUST być odrzucona przy starcie.

Reguła jest tą samą, którą mają schematy agenta, zespołów, archiwum i obserwacji rynków
predykcyjnych — i z tych samych powodów: lokalny moduł nie pisze do produkcji, poświadczenie
ambientowe nie podszywa modułu, sekret nie mieszka w adresie.

#### Scenario: Host zdalny bez tożsamości

- **WHEN** moduł startuje bez skonfigurowanej roli, a adres wskazuje hosta spoza pętli zwrotnej
- **THEN** moduł odmawia startu, wskazując ograniczenie pracy bez tożsamości do bazy lokalnej

#### Scenario: Poświadczenie w adresie obok tożsamości

- **WHEN** moduł startuje w trybie tożsamości, a adres bazy niesie nazwę użytkownika lub hasło
- **THEN** moduł odmawia startu

#### Scenario: Host zdalny bez wymuszonego szyfrowania

- **WHEN** moduł startuje w trybie tożsamości z adresem hosta zdalnego bez wymogu szyfrowania
- **THEN** moduł odmawia startu, wskazując konfigurację połączenia jako przyczynę

### Requirement: Własna baza, cudzych tabel nie dotyka

Baza platformy MUST być odrębna od baz pozostałych modułów: moduł MUST NOT czytać ani pisać
w tabelach należących do innego modułu, a jego migracje MUST NOT dotykać niczego poza jego
własną bazą. Rola modułu MUST NOT mieć dostępu do baz pozostałych modułów.

#### Scenario: Migracje platformy

- **WHEN** migracje platformy zostają wykonane
- **THEN** dotyczą wyłącznie jej własnej bazy

### Requirement: Moduł sam migruje swoją bazę, pod blokadą, i odmawia przy rozjeździe

Moduł MUST doprowadzić własną bazę do rewizji schematu swojego obrazu, zanim zacznie
odpowiadać, bez osobnego kroku operatora przy wdrożeniu. Migracja MUST przebiegać pod
blokadą wyłączną trzymaną w bazie, z kresem czekania; proces, który się nie doczekał,
MUST odmówić pracy. Migracje MUST biec tą samą tożsamością, którą moduł pracuje, a obiekt
utworzony przez migrację MUST być użyteczny bez osobnego nadania uprawnień. Gdy po migracji
rewizja bazy różni się od rewizji obrazu — w którąkolwiek stronę — moduł MUST odmówić pracy,
nazywając obie rewizje.

Jedyny krok operatora, dokładnie raz na nową bazę: nadanie roli własności schematu, zanim
pierwsze wdrożenie spróbuje migrować.

#### Scenario: Wdrożenie niosące nową rewizję

- **WHEN** moduł startuje z obrazem nowszym niż rewizja jego bazy
- **THEN** brakujące migracje wykonuje dokładnie jeden proces, pod blokadą
- **AND** moduł zaczyna odpowiadać dopiero po nich

#### Scenario: Baza wyprzedza obraz

- **WHEN** moduł startuje przeciwko bazie na rewizji nowszej niż jego obraz
- **THEN** odmawia pracy, nazywając obie rewizje

#### Scenario: Nowa tabela jest od razu użyteczna

- **WHEN** migracja tworzy nową tabelę
- **THEN** moduł czyta z niej i pisze do niej bez osobnego nadania uprawnień


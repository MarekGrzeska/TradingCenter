# terminal-telegram Specification

## Purpose
TBD - created by archiving change telegram-bots-from-the-terminal. Update Purpose after archive.
## Requirements
### Requirement: Zakładka pokazuje konto, boty, adresatów i cele

Zakładka MUST pokazywać zalogowane konto (albo to, że go nie ma i dlaczego), listę botów z liczbą
wobec sufitu oraz adresatów każdego bota z ich stanem. Zakładka MUST NOT pokazywać celów ani
przypisań. MUST natomiast odsyłać do zakładki Alerty jako miejsca, w którym decyduje się, kto o czym
słyszy.

#### Scenario: Brama bez niczego

- **WHEN** operator otwiera zakładkę, a brama nie ma konta, botów ani adresatów
- **THEN** zakładka MUST mówić, od czego zacząć, zamiast pokazywać puste tabele

#### Scenario: Brama nieosiągalna

- **WHEN** trasa stanu bramy nie odpowiada
- **THEN** zakładka MUST powiedzieć, że brama nie odpowiada, i MUST NOT pokazywać list jako pustych

### Requirement: Logowanie konta z zakładki ostrzega, czyje to ma być konto

Przed podaniem numeru zakładka MUST mówić, że konto powinno być dedykowanym kontem do botów, a nie
prywatnym kontem operatora. Pole hasła MUST być maskowane. Brak ustawienia klucza sesji MUST być
pokazany jako nazwane ustawienie do dodania, nie jako błąd logowania.

#### Scenario: Logowanie z hasłem dwuetapowym

- **WHEN** operator podaje numer i kod, a brama odpowiada, że czeka na hasło
- **THEN** zakładka MUST pokazać pole hasła w tym samym przebiegu, bez zaczynania od nowa

### Requirement: Bot powstaje z zakładki i od razu prowadzi do aktywacji

Z zalogowanym kontem zakładka MUST pozwalać założyć bota z tytułu i nazwy, bez zalogowanego — wkleić
token. Po założeniu albo wklejeniu zakładka MUST od razu zaproponować adresata i pokazać jego
odnośnik startowy jako link i kod QR, mówiąc, ile czasu zostało do jego wygaśnięcia, i MUST sama
zauważyć tapnięcie, bez przeładowania strony.

#### Scenario: Tapnięcie z telefonu

- **WHEN** operator skanuje kod QR i dotyka „Start” w Telegramie
- **THEN** zakładka MUST pokazać adresata jako odbierającego w ciągu kilku sekund

#### Scenario: Odnośnik wygasł

- **WHEN** odnośnik wygasa przed tapnięciem
- **THEN** zakładka MUST to powiedzieć i MUST pozwolić wydać nowy jednym działaniem

### Requirement: Działania nieodwracalne pytają, a odmowa mówi dlaczego

Usunięcie bota, usunięcie adresata, rotacja tokenu i wylogowanie konta MUST wymagać potwierdzenia.
Potwierdzenie usunięcia bota albo adresata MUST mówić, że reguły alertów, które go wskazują, przestaną
doręczać. Odmowa bramy MUST być pokazana słowami bramy.

#### Scenario: Usunięcie adresata

- **WHEN** operator prosi o usunięcie adresata
- **THEN** zakładka MUST zapytać o potwierdzenie i MUST powiedzieć, że reguły wskazujące tego adresata przestaną doręczać


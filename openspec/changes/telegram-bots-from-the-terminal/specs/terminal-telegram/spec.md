## Purpose

Zakładka terminala nad bramą Telegrama: konto-właściciel, boty, adresaci i cele w jednym miejscu,
tak żeby nic z tego nie wymagało już `curl`-a ani zmiany ustawień.

## ADDED Requirements

### Requirement: Zakładka pokazuje konto, boty, adresatów i cele

Zakładka MUST pokazywać zalogowane konto (albo to, że go nie ma i dlaczego), listę botów z liczbą
wobec sufitu, adresatów każdego bota z ich stanem oraz listę celów z ich adresatem. Cel, który nie
ma adresata, MUST być wyróżniony, a ich liczba MUST być widoczna bez przewijania listy.

#### Scenario: Brama bez niczego

- **WHEN** operator otwiera zakładkę, a brama nie ma konta, botów ani przypisań
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

### Requirement: Przypisania zmienia się na liście celów

Dla każdego celu zakładka MUST pokazywać adresata, który go dziś dostaje, i to, czy pochodzi z
przypisania tego celu, z przedrostka, czy z przypisania domyślnego. Operator MUST móc przypisać,
przepiąć i zdjąć przypisanie celu, przedrostka i przypisania domyślnego.

#### Scenario: Cel dziedziczy adresata

- **WHEN** cel `youtube.film` nie ma własnego przypisania, a `youtube` ma
- **THEN** zakładka MUST pokazać adresata z `youtube` i MUST nazwać przypisanie, z którego pochodzi

### Requirement: Działania nieodwracalne pytają, a odmowa mówi dlaczego

Usunięcie bota, usunięcie adresata, rotacja tokenu i wylogowanie konta MUST wymagać potwierdzenia.
Odmowa bramy — w szczególności usunięcie bota albo adresata, na którym wisi przypisanie — MUST być
pokazana słowami bramy, z nazwami celów, które trzeba najpierw przepiąć.

#### Scenario: Usunięcie bota z przypisaniem

- **WHEN** operator potwierdza usunięcie bota, którego adresat ma przypisane cele
- **THEN** zakładka MUST pokazać odmowę z listą tych celów, a bot MUST zostać na liście

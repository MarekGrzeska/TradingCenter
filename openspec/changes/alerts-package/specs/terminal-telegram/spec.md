## MODIFIED Requirements

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

### Requirement: Działania nieodwracalne pytają, a odmowa mówi dlaczego

Usunięcie bota, usunięcie adresata, rotacja tokenu i wylogowanie konta MUST wymagać potwierdzenia.
Potwierdzenie usunięcia bota albo adresata MUST mówić, że reguły alertów, które go wskazują, przestaną
doręczać. Odmowa bramy MUST być pokazana słowami bramy.

#### Scenario: Usunięcie adresata

- **WHEN** operator prosi o usunięcie adresata
- **THEN** zakładka MUST zapytać o potwierdzenie i MUST powiedzieć, że reguły wskazujące tego adresata przestaną doręczać

## REMOVED Requirements

### Requirement: Przypisania zmienia się na liście celów
**Reason**: Cele i przypisania zniknęły z bramy.
**Migration**: `terminal-alerts`: kreator reguł.

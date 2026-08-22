# terminal-accounts Specification

## Purpose
Opisuje ekran rachunku w terminalu: co operator widzi o kontach demo bez pytania agenta, jak
często to się odświeża i co może z tego ekranu zrobić z pieniędzmi oraz z tym, które konto
jest aktywne.
## Requirements
### Requirement: Ekran pokazuje konta demo i ich stan

Terminal MUST mieć ekran wyliczający konta demo osiągalne poświadczeniami modułu. Każde konto
MUST nieść nazwę, walutę, saldo, środki dostępne i wynik, a dokładnie jedno MUST być
oznaczone jako aktywne — to, na którym dzieje się handel.

Ekran MUST pokazywać otwarte pozycje **konta aktywnego**. MUST NOT pokazywać pozycji
pozostałych kont ani udawać, że ich nie ma: dostawca wiąże pozycje z kontem aktywnym sesji,
więc pozycje innego konta wymagałyby przełączenia się na nie, a przełączenie ma skutki poza
tym ekranem.

Ekran MUST odświeżać stan cyklicznie, bez działania operatora, i MUST mówić, kiedy ostatnio
mu się to udało. Odczyt, który zawiódł, MUST być powiedziany wprost i MUST NOT być pokazany
jako rachunek pusty ani jako stan sprzed awarii bez adnotacji.

#### Scenario: Operator otwiera ekran

- **WHEN** operator otwiera ekran rachunku
- **THEN** widzi listę kont demo z saldem, środkami dostępnymi i wynikiem
- **AND** konto aktywne jest odróżnione od pozostałych
- **AND** widzi otwarte pozycje konta aktywnego

#### Scenario: Stan zmienia się bez działania operatora

- **WHEN** saldo albo pozycja zmieniają się po stronie dostawcy
- **THEN** ekran pokazuje nowy stan bez przeładowania strony przez operatora

#### Scenario: Odczyt zawiódł

- **WHEN** odczyt rachunku kończy się błędem
- **THEN** ekran mówi to wprost
- **AND** MUST NOT pokazać zera ani pustej listy jako stanu rachunku

### Requirement: Operator dokłada środki na konto demo z ekranu

Ekran MUST pozwalać zmienić saldo konta demo o zadaną kwotę. Kwota ujemna MUST być
dozwolona — ustawienie chudego rachunku jest przygotowaniem próby, nie pomyłką.

Po wykonaniu ekran MUST pokazać saldo po zmianie, bez pytania operatora o odświeżenie.
Odmowa — sufit salda, zakres kwoty, wyczerpany limit dobowy — MUST być powiedziana z
powodem podanym przez moduł, a saldo na ekranie MUST NOT zmienić się o kwotę, której nie
przyjęto.

#### Scenario: Dołożenie środków

- **WHEN** operator podaje kwotę i zatwierdza
- **THEN** ekran pokazuje saldo po zmianie

#### Scenario: Moduł odmawia korekty

- **WHEN** moduł odmawia korekty salda
- **THEN** ekran podaje powód odmowy
- **AND** pokazane saldo pozostaje tym sprzed próby

### Requirement: Przełączenie konta mówi, co zrywa

Ekran MUST pozwalać uczynić inne konto demo aktywnym. Zanim to zrobi, MUST powiedzieć, że
przełączenie zrywa strumień notowań, którym zbierane są świece, i że przerwa dotyczy
zbierania danych, a nie tego ekranu.

Po przełączeniu ekran MUST pokazywać pozycje konta, które właśnie stało się aktywne.

#### Scenario: Operator przełącza konto

- **WHEN** operator wybiera inne konto jako aktywne
- **THEN** ekran mówi, że przełączenie zrywa strumień notowań, zanim je wykona
- **AND** po wykonaniu pokazuje pozycje nowego konta aktywnego

#### Scenario: Przełączenie odmówione

- **WHEN** moduł odmawia przełączenia
- **THEN** ekran podaje powód
- **AND** konto aktywne na ekranie pozostaje tym, którym było


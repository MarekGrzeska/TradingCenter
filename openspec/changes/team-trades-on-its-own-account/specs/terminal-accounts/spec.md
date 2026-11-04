## MODIFIED Requirements

### Requirement: Ekran pokazuje konta demo i ich stan

Terminal MUST mieć ekran wyliczający konta demo osiągalne poświadczeniami modułu. Każde konto
MUST nieść nazwę, walutę, saldo, środki dostępne i wynik, a dokładnie jedno MUST być
oznaczone jako aktywne, czyli to, na którym działa handel bez wskazanego konta.

Ekran MUST pokazywać otwarte pozycje konta wybranego przez operatora, a bez wyboru konta
aktywnego. Wybór konta do oglądania MUST NOT przełączać konta aktywnego: zespół handlujący na
koncie aktywnym nie może stracić konta dlatego, że operator chciał zobaczyć pozycje innego.
Ekran MUST mówić, które konto pokazuje i czy to konto aktywne.

Ekran MUST odświeżać stan cyklicznie, bez działania operatora, i MUST mówić, kiedy ostatnio
mu się to udało. Odczyt, który zawiódł, MUST być powiedziany wprost i MUST NOT być pokazany
jako rachunek pusty ani jako stan sprzed awarii bez adnotacji.

#### Scenario: Operator otwiera ekran

- **WHEN** operator otwiera ekran rachunku
- **THEN** widzi listę kont demo z saldem, środkami dostępnymi i wynikiem
- **AND** konto aktywne jest odróżnione od pozostałych
- **AND** widzi otwarte pozycje konta aktywnego

#### Scenario: Operator ogląda pozycje innego konta

- **WHEN** operator wybiera do oglądania konto inne niż aktywne
- **THEN** ekran pokazuje pozycje wybranego konta
- **AND** konto aktywne pozostaje tym, którym było

#### Scenario: Stan zmienia się bez działania operatora

- **WHEN** saldo albo pozycja zmieniają się po stronie dostawcy
- **THEN** ekran pokazuje nowy stan bez przeładowania strony przez operatora

#### Scenario: Odczyt zawiódł

- **WHEN** odczyt rachunku kończy się błędem
- **THEN** ekran mówi to wprost
- **AND** MUST NOT pokazać zera ani pustej listy jako stanu rachunku

### Requirement: Przełączenie konta mówi, co zrywa

Ekran MUST pozwalać uczynić inne konto demo aktywnym. Zanim to zrobi, MUST powiedzieć, że
konto aktywne jest wspólne dla wszystkich wołających, którzy nie wskazują konta (rozmowy,
zespołów bez przypisanego konta i klienta MCP operatora), i że ich kolejne zlecenia trafią na
nowe konto. Zespołów z przypisanym kontem przełączenie nie dotyczy.

Po przełączeniu ekran MUST pokazywać pozycje konta, które właśnie stało się aktywne.

#### Scenario: Operator przełącza konto

- **WHEN** operator wybiera inne konto jako aktywne
- **THEN** ekran mówi, kogo przełączenie dotyczy, zanim je wykona
- **AND** po wykonaniu pokazuje pozycje nowego konta aktywnego

#### Scenario: Przełączenie odmówione

- **WHEN** moduł odmawia przełączenia
- **THEN** ekran podaje powód
- **AND** konto aktywne na ekranie pozostaje tym, którym było

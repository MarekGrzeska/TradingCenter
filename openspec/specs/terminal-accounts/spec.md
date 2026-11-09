# terminal-accounts Specification

## Purpose
Opisuje ekran rachunku w terminalu: co operator widzi o kontach demo bez pytania agenta, jak
często to się odświeża i co może z tego ekranu zrobić z pieniędzmi oraz z tym, które konto
jest aktywne.
## Requirements
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

### Requirement: Ekran pokazuje konto realne osobno od kont demo

Gdy terminal ma skonfigurowany adres procesu konta realnego, ekran rachunku MUST pokazywać konto realne w osobnej
sekcji, odróżnionej od kont demo tak, żeby nie dało się ich pomylić: nazwa, waluta, saldo, środki dostępne, wynik,
otwarte pozycje i zlecenia oczekujące. Sekcja MUST odświeżać się cyklicznie i MUST mówić, kiedy ostatnio się to udało;
odczyt, który zawiódł, MUST być powiedziany wprost, a MUST NOT być pokazany jako konto puste. Bez skonfigurowanego adresu
sekcji MUST NOT być.

Ekran MUST NOT pozwalać na koncie realnym na korektę salda, przełączenie konta ani złożenie zlecenia.

#### Scenario: Operator otwiera ekran z kontem realnym

- **WHEN** operator otwiera ekran rachunku, a adres procesu konta realnego jest skonfigurowany
- **THEN** widzi konto realne w osobnej sekcji, z saldem, pozycjami i zleceniami oczekującymi
- **AND** sekcja nie oferuje korekty salda ani przełączenia konta

#### Scenario: Odczyt konta realnego zawiódł

- **WHEN** odczyt konta realnego kończy się błędem
- **THEN** sekcja mówi to wprost
- **AND** MUST NOT pokazać zera ani pustej listy jako stanu konta realnego

#### Scenario: Konto realne nieskonfigurowane

- **WHEN** adres procesu konta realnego nie jest skonfigurowany
- **THEN** ekran pokazuje wyłącznie konta demo, tak jak przed tą zmianą

### Requirement: Operator zamyka wszystko na koncie realnym z ekranu

Sekcja konta realnego MUST mieć jedno działanie zapisujące: zamknięcie wszystkich pozycji i anulowanie wszystkich zleceń
oczekujących. Przed wykonaniem MUST zapytać o potwierdzenie, mówiąc, że dotyczy konta realnego i ilu pozycji oraz
zleceń. Po wykonaniu MUST pokazać skutek każdej pozycji i każdego zlecenia, a niezamknięte MUST nazwać z powodem.

#### Scenario: Operator zamyka wszystko

- **WHEN** operator wybiera zamknięcie wszystkiego i potwierdza
- **THEN** ekran pokazuje skutek dla każdej pozycji i każdego zlecenia
- **AND** odświeżona sekcja nie pokazuje już zamkniętych pozycji

#### Scenario: Operator rezygnuje przy potwierdzeniu

- **WHEN** operator wybiera zamknięcie wszystkiego, a potem rezygnuje przy potwierdzeniu
- **THEN** nic nie zostaje wysłane

#### Scenario: Część pozycji nie zamknięta

- **WHEN** moduł odpowiada, że jednej pozycji nie zamknął
- **THEN** ekran nazywa tę pozycję i powód


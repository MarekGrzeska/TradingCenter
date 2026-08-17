# teams-database-connection Specification

## Purpose
Czym moduł przedstawia się swojej bazie, jak chroni połączenie do bazy zdalnej, czyja jest ta
baza i jak sam doprowadza ją do rewizji, dla której powstał, bez kroku po stronie operatora.
## Requirements
### Requirement: Moduł przedstawia się tożsamością, nie hasłem

Wobec bazy zdalnej moduł MUST uwierzytelniać się poświadczeniem wystawianym dla jego tożsamości
i pobieranym przy nawiązywaniu połączenia; trwałe hasło do bazy zdalnej MUST NOT być wymagane
do pracy modułu ani przechowywane w jego konfiguracji. Tryb tożsamości wybiera skonfigurowana
nazwa roli; konfiguracja trybu tożsamości, której adres bazy niesie własne poświadczenie, MUST
być odrzucona przy starcie.

Poświadczenie ma ważność krótszą niż czas pracy modułu i MUST być odnawiane tak, by połączenie
nawiązywane po jego wygaśnięciu zestawiało się poprawnie.

#### Scenario: Poświadczenia nie da się uzyskać

- **WHEN** moduł startuje w trybie tożsamości, a wystawca poświadczeń jest nieosiągalny lub
  odmawia
- **THEN** moduł odmawia startu, wskazując uzyskanie poświadczenia jako przyczynę
- **AND** MUST NOT sięgać po zapasowe hasło

#### Scenario: Nowe połączenie po wygaśnięciu poświadczenia

- **WHEN** moduł pracuje dłużej niż okres ważności poświadczenia i potrzebuje nowego połączenia
- **THEN** połączenie zestawia się na odnowionym poświadczeniu

### Requirement: Połączenie z bazą zdalną jest szyfrowane

Połączenie do bazy spoza maszyny modułu MUST być szyfrowane, a konfiguracja trybu tożsamości
bez wymuszonego szyfrowania MUST być odrzucona przy starcie.

#### Scenario: Tryb tożsamości bez wymuszonego szyfrowania

- **WHEN** moduł startuje w trybie tożsamości, a adres bazy nie wymusza szyfrowania
- **THEN** moduł odmawia startu, wskazując szyfrowanie jako przyczynę

### Requirement: Praca bez tożsamości nie wychodzi poza maszynę

Moduł uruchomiony bez skonfigurowanej nazwy roli MUST łączyć się wyłącznie z bazą w pętli
zwrotnej i MUST odmówić startu, gdy adres wskazuje host inny niż lokalny. Jest to tryb pracy
lokalnej, a ustawienie, przy którym praca lokalna sięga bazy zdalnej, MUST NOT dać się złożyć
przez nieuwagę.

#### Scenario: Tryb lokalny ze zdalnym adresem

- **WHEN** moduł startuje bez skonfigurowanej nazwy roli, a adres bazy wskazuje host spoza
  pętli zwrotnej
- **THEN** moduł odmawia startu, wskazując adres jako przyczynę

### Requirement: Moduł nie dzieli bazy z innym modułem

Baza tego modułu MUST być odrębna od bazy archiwum świec i od bazy modułu agenta: moduł MUST
NOT czytać ani pisać w tabelach należących do innego modułu, a jego migracje MUST NOT dotykać
niczego poza jego własną bazą. Dwa moduły w jednej bazie logicznej nie dają się osobno wdrożyć,
przywrócić z kopii ani usunąć, a to właśnie te trzy rzeczy czynią moduł niezależnym.

#### Scenario: Migracje modułu

- **WHEN** migracje tego modułu zostają wykonane
- **THEN** dotyczą wyłącznie jego własnej bazy
- **AND** żadna tabela archiwum świec ani modułu agenta nie zostaje zmieniona

#### Scenario: Poświadczenie nie sięga dalej

- **WHEN** moduł łączy się w trybie tożsamości
- **THEN** jego rola MUST NOT mieć dostępu do bazy archiwum świec ani do bazy modułu agenta

### Requirement: Poświadczenie nie wycieka do logów

Moduł MUST NOT zapisywać w dzienniku ani zwracać w odpowiedzi poświadczenia do bazy, jego
fragmentu ani adresu niosącego poświadczenie. Komunikat o nieudanym połączeniu MUST nazywać
przyczynę bez cytowania poświadczenia.

#### Scenario: Nieudane połączenie trafia do dziennika

- **WHEN** zestawienie połączenia z bazą kończy się błędem
- **THEN** wpis w dzienniku nazywa przyczynę
- **AND** nie niesie poświadczenia ani jego fragmentu

### Requirement: Moduł sam doprowadza bazę do rewizji, dla której powstał

Moduł MUST wykonać migracje swojej bazy do rewizji odpowiadającej wdrożonemu obrazowi, zanim
zacznie cokolwiek obsługiwać, i MUST zrobić to sam, przy starcie. Doprowadzenie bazy do rewizji
MUST NOT wymagać kroku po stronie operatora ani przed wdrożeniem, ani po nim.

Scalenie kodu MUST zostawiać produkcję działającą. Wdrożenie, przy którym baza zostaje na
rewizji starszej niż obraz, to moduł, który wstał i nie działa — a płaszczyzna sterowania
platformy pokaże go wtedy jako wdrożony poprawnie.

#### Scenario: Wdrożenie obrazu z nową rewizją

- **WHEN** zostaje wdrożony obraz niosący migracje nowsze niż stan bazy
- **THEN** moduł wykonuje je przy starcie, zanim zacznie odpowiadać
- **AND** operator nie wykonuje żadnego kroku

### Requirement: Migruje dokładnie jeden proces naraz

Gdy kilka procesów modułu startuje równocześnie, MUST migrować dokładnie jeden; pozostałe MUST
zaczekać na zakończenie migracji i dopiero potem zacząć obsługiwać. Oczekiwanie MUST mieć
skończoną granicę, a proces, który jej nie doczekał, MUST odmówić pracy zamiast obsługiwać przy
niepewnym stanie bazy.

Blokada MUST być zwalniana wraz z zakończeniem procesu, który ją trzymał — także wtedy, gdy
zakończył się nagle. Blokada wymagająca sprzątania po awarii zamieniłaby jedno rzadkie zdarzenie
w drugie, o które trzeba prosić operatora.

#### Scenario: Dwa procesy startują równocześnie

- **WHEN** dwa procesy modułu startują w tej samej chwili przy bazie wymagającej migracji
- **THEN** jeden wykonuje migracje, a drugi czeka
- **AND** obydwa zaczynają obsługiwać po zakończeniu migracji

#### Scenario: Proces trzymający blokadę ginie

- **WHEN** proces wykonujący migracje kończy się nagle
- **THEN** blokada przestaje obowiązywać bez działania operatora

### Requirement: Moduł jest właścicielem tego, co jego migracje tworzą

Migracje MUST być wykonywane tożsamością, którą moduł posługuje się w pracy, tak by utworzone
obiekty należały do niej. Praca modułu na własnych tabelach MUST NOT wymagać nadania uprawnień
po utworzeniu.

Uprawnienie nadawane po fakcie jest zawsze uprawnieniem, o którym ktoś zapomni, a jego brak
objawia się odmową dostępu do tabeli, która istnieje — czyli komunikatem wskazującym w złą
stronę.

#### Scenario: Migracja tworzy nową tabelę

- **WHEN** migracja tworzy tabelę, a moduł zaczyna z niej korzystać
- **THEN** korzysta bez osobnego nadania uprawnień

### Requirement: Moduł, który nie zdołał zmigrować, nie udaje że działa

Moduł MUST sprawdzić po migracji, że stan bazy odpowiada rewizji wdrożonego obrazu, i MUST
odmówić obsługi, gdy jest inaczej — zarówno gdy baza pozostała za obrazem, jak i gdy wyprzedza
go po wycofaniu kodu. Sprawdzenie wdrożenia MUST sięgać procesu modułu, a MUST NOT poprzestawać
na płaszczyźnie sterowania platformy.

#### Scenario: Baza wyprzedza wycofany obraz

- **WHEN** obraz zostaje wycofany do wersji starszej niż rewizja, na której stoi baza
- **THEN** moduł odmawia obsługi, wskazując rozbieżność jako przyczynę

#### Scenario: Sprawdzenie wdrożenia

- **WHEN** wdrożenie sprawdza, czy się powiodło
- **THEN** pyta proces modułu
- **AND** wdrożenie, którego proces nie wstał, MUST zostać uznane za nieudane


## ADDED Requirements

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

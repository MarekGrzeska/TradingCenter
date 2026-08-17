# trading-mcp-execution Specification

## Purpose
Co narzędzie zapisujące oddaje modelowi po tym, jak zlecenie poszło do providera: kiedy wynik
jest rozliczony, jak nazywa się wynik nierozliczony i dlaczego moduł nigdy nie powtarza
zlecenia po własnej awarii.
## Requirements
### Requirement: Wynik zlecenia jest rozliczony albo nazwany jako nierozliczony

Narzędzie zapisujące MUST oddać modelowi wynik, który albo jest rozliczony — wykonane,
oczekujące, zamknięte, anulowane, zmienione, odrzucone — albo jest jawnie oznaczony jako
nierozliczony i niesie referencję pozwalającą sprawdzić go później. Wynik nierozliczony
MUST NOT być podany jako wykonanie.

#### Scenario: Zlecenie rynkowe wykonane

- **WHEN** model składa zlecenie MARKET na handlowalnym symbolu i provider je wykonuje
- **THEN** wynik niesie identyfikator zlecenia i poziom wykonania

#### Scenario: Rozliczenie nie przychodzi na czas

- **WHEN** gateway oddaje wynik oznaczony jako oczekujący na rozliczenie
- **THEN** model dostaje ten sam stan, nazwany jako nierozliczony, wraz z referencją
- **AND** wynik MUST NOT być przedstawiony jako wykonanie ani jako odrzucenie

#### Scenario: Provider odrzuca zlecenie

- **WHEN** provider odrzuca zlecenie
- **THEN** wynik jest oznaczony jako odrzucony i niesie powód podany przez providera

### Requirement: Moduł nie ponawia zlecenia po własnej awarii

Po nieudanym wywołaniu gatewaya — przekroczonym czasie, zerwanym połączeniu, błędzie po
stronie serwera — moduł MUST NOT powtórzyć żądania zmieniającego stan rachunku. MUST oddać
modelowi wynik nazywający awarię dostępu i to, że skutek żądania jest nieznany.

Provider nie przyjmuje klucza idempotencji, więc powtórzone zlecenie jest **drugą pozycją**,
a nie ponowieniem pierwszej. Ryzyko przeciwne — zlecenie złożone, o którym model nie wie —
jest odwracalne odczytem rachunku, i po to narzędzia czytające są w tym samym zestawie.

#### Scenario: Zerwane połączenie w trakcie składania zlecenia

- **WHEN** wywołanie gatewaya nie kończy się odpowiedzią
- **THEN** moduł MUST NOT wysłać żądania ponownie
- **AND** model dostaje wynik nazywający awarię dostępu i nieznany skutek

#### Scenario: Model sprawdza skutek nieudanego wywołania

- **WHEN** model po awarii dostępu odczytuje pozycje i zlecenia oczekujące
- **THEN** widzi stan rachunku taki, jaki jest teraz
- **AND** może na tej podstawie rozstrzygnąć, czy zlecenie doszło

### Requirement: Wywołanie gatewaya ma skończony czas

Każde wywołanie gatewaya MUST mieć górną granicę czasu oczekiwania. Jej przekroczenie MUST być
zgłoszone jako awaria dostępu i MUST kończyć oczekiwanie, a nie przedłużać je kolejną próbą.

#### Scenario: Gateway odpowiada wolniej niż granica

- **WHEN** gateway nie odpowiada w dozwolonym czasie
- **THEN** narzędzie kończy oczekiwanie i zgłasza awarię dostępu

